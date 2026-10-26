"""BTC-копилка на 5-летних прогонах: полный отчёт по долям и долларам.

ЗАЧЕМ
Владелец (25.10.26): «Потом новых кандидатов прогнать дополнительно биткоин
копилкой. Учесть, сколько биткоина скопилось, сколько самого актива стало в
долларах, сколько совокупно актив + биткоин.»

То есть по каждому кандидату нужны ЧЕТЫРЕ числа, а не одно:
  1. сколько BTC накоплено (в штуках);
  2. сколько стал стоить исходный актив (в долларах);
  3. сколько стоит накопленный BTC (в долларах);
  4. сколько СОВОПУПНО актив + BTC + кэш (в долларах) — и как это соотносится
     с базовой стратегией без копилки.

ЧТО ЧИТАЕТСЯ
wiki/founder/scan5y/returns/<idx>.npz — дневная доходность каждого прогона
(её сохранил scan5y.py). Рядом в scan-results.jsonl лежат метрики прогона.

ЧТО СЧИТАЕТСЯ
Копилка владельца (правила из btc_kopilka_13.py, те же константы):
  - порог фиксации: рост стратегической доли на lock_threshold (30%);
  - в BTC уходит lock_share_of_gain (75%) этого ПРИРОСТА;
  - возврат: при подтверждённом дне (откат >= drawdown_trigger, восстановление
    >= половины глубины, цена выше своей 50-дневной средней) в актив
    возвращается return_share_of_btc (30%) резерва;
  - комиссия 10 bps на каждую ногу (продажа стратегии + покупка BTC).
Правило причинное: дно определяется по прошлым барам, будущее не читается.

ОГОВОРКИ (попадают в артефакт)
- Наложение применяется к реализованной дневной доходности стратегии, а не
  к повторному прогону движка со смешанным BTC-рукавом.
- Цена актива берётся из локальных биржевых CSV (тот же источник, что и
  доходность), цена BTC — из BTCUSDT.csv.
- Комиссия движка (maker/taker/проскальзывание) уже учтена в доходности
  стратегии; в копилке считается только комиссия ПЕРЕВОДОВ.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
SCAN = FOUNDER / "scan5y"
RESULTS = SCAN / "scan-results.jsonl"
RETURNS = SCAN / "returns"
OUT = SCAN / "kopilka.json"

sys.path.insert(0, str(FOUNDER))

# Константы владельца — те же, что в btc_kopilka_13.py.
LOCK_THRESHOLD = 0.30
LOCK_SHARE = 0.75
RETURN_SHARE = 0.30
DRAWDOWN_TRIGGER = 0.10
MA_WINDOW = 50
COST = 0.001
START_CAPITAL = 100.0

CSV_DIR = REPO / "data" / "binance-spot-1d"


def _load_close(symbol: str) -> pd.Series:
    path = CSV_DIR / f"{symbol}.csv"
    frame = pd.read_csv(path)
    dc = "date" if "date" in frame.columns else frame.columns[0]
    frame[dc] = pd.to_datetime(frame[dc])
    series = frame.set_index(dc)["close"].astype(float)
    return series[~series.index.duplicated(keep="last")].sort_index()


def _btc_close() -> pd.Series:
    return _load_close("BTCUSDT")


def run_kopilka(
    strategy_equity: pd.Series,
    asset_close: pd.Series,
    btc_close: pd.Series,
    lock_threshold: float = LOCK_THRESHOLD,
    lock_share: float = LOCK_SHARE,
    return_share: float = RETURN_SHARE,
) -> dict[str, Any]:
    """Наложение копилки. Возвращает состав счёта в конце."""
    idx = strategy_equity.index.intersection(btc_close.index).intersection(asset_close.index)
    if len(idx) < 60:
        return {"status": "SKIPPED", "reason": "insufficient overlap"}

    unit_price = strategy_equity.reindex(idx).astype(float)
    btc_price = btc_close.reindex(idx).ffill().astype(float)
    asset_price = asset_close.reindex(idx).ffill().astype(float)
    asset_ma = asset_price.rolling(MA_WINDOW, min_periods=MA_WINDOW).mean()

    cash = 0.0
    strategy_units = START_CAPITAL / float(unit_price.loc[idx[0]])
    btc_units = 0.0
    lock_reference = START_CAPITAL
    peak_value = START_CAPITAL
    trough_value = START_CAPITAL
    episode_returned = False
    locks = 0
    returns_done = 0
    equity_curve: list[float] = []

    for date in idx:
        sp = float(unit_price.loc[date])
        bp = float(btc_price.loc[date])
        strategy_value = strategy_units * sp
        btc_value = btc_units * bp
        total = strategy_value + btc_value + cash

        # Правило 1: фиксация прироста в BTC.
        if strategy_value >= lock_reference * (1.0 + lock_threshold) and strategy_value > 0:
            gain = strategy_value - lock_reference
            move = lock_share * gain
            fee = move * COST
            units_sold = move / sp
            strategy_units -= units_sold
            cash += move - fee
            btc_gross = cash / (1.0 + COST)
            btc_fee = btc_gross * COST
            btc_units += btc_gross / bp
            cash -= btc_gross + btc_fee
            lock_reference = strategy_units * sp
            locks += 1

        # Правило 2: возврат резерва в актив при подтверждённом дне.
        # ВАЖНО: возврат возможен ТОЛЬКО если есть что возвращать
        # (btc_units > 0). Без этой проверки счёт обнулялся: кэш покупал
        # актив, а актив стоил ноль, и годовая доходность становилась -100%.
        # Правило идентично btc_kopilka_13.run_overlay.
        drawdown = (total / peak_value - 1.0) if peak_value > 0 else 0.0
        trough_value = min(trough_value, total)
        ma_value = asset_ma.loc[date]
        depth = peak_value - trough_value
        recovery = (total - trough_value) / depth if depth > 0 else 0.0
        confirmed = (
            not episode_returned
            and drawdown <= -DRAWDOWN_TRIGGER
            and recovery >= 0.5
            and (not np.isnan(ma_value))
            and float(asset_price.loc[date]) > float(ma_value)
        )
        if confirmed and btc_units > 0 and return_share > 0:
            sell_units = btc_units * return_share
            gross = sell_units * bp
            fee = gross * COST
            btc_units -= sell_units
            cash += gross - fee
            # покупаем юниты стратегии на кэш (комиссия второй ноги)
            spend = cash
            units_bought = spend / (sp * (1.0 + COST))
            strategy_units += units_bought
            cash = 0.0
            returns_done += 1
            episode_returned = True

        total = strategy_units * sp + btc_units * bp + cash
        equity_curve.append(total)
        if total > peak_value:
            # новый максимум — новая эпизодная ветка для правила возврата
            peak_value = total
            trough_value = total
            episode_returned = False

    equity = pd.Series(equity_curve, index=idx)
    daily = equity.pct_change().dropna()
    final_value = float(equity.iloc[-1])
    final_btc_units = float(btc_units)
    final_btc_price = float(btc_price.loc[idx[-1]])
    final_asset_value = float(strategy_units * float(unit_price.loc[idx[-1]]))
    final_btc_value = final_btc_units * final_btc_price
    final_cash = float(cash)

    n = len(daily)
    annual = float((1.0 + daily).prod() ** (365.0 / n) - 1.0) * 100.0 if n else None
    eq = (1.0 + daily).cumprod()
    dd = float((eq / eq.cummax() - 1.0).min()) * 100.0
    std = float(daily.std(ddof=1))
    t_stat = float(daily.mean() / std * (n ** 0.5)) if std > 0 and n else None

    return {
        "status": "OK",
        "n_obs": n,
        "annual_pct": annual,
        "max_dd_pct": dd,
        "t_stat": t_stat,
        "final_value": final_value,
        "final_btc_units": final_btc_units,
        "final_btc_price": final_btc_price,
        "final_btc_value": final_btc_value,
        "final_asset_value": final_asset_value,
        "final_cash": final_cash,
        "btc_share_pct": (final_btc_value / final_value * 100.0) if final_value > 0 else 0.0,
        "asset_share_pct": (final_asset_value / final_value * 100.0) if final_value > 0 else 0.0,
        "locks": locks,
        "returns_to_asset": returns_done,
    }


def _stats(returns: pd.Series) -> dict[str, Any]:
    clean = returns.dropna()
    n = len(clean)
    if n < 2:
        return {}
    equity = (1.0 + clean).cumprod()
    std = float(clean.std(ddof=1))
    return {
        "annual_pct": float((1.0 + clean).prod() ** (365.0 / n) - 1.0) * 100.0,
        "max_dd_pct": float((equity / equity.cummax() - 1.0).min()) * 100.0,
        "t_stat": float(clean.mean() / std * (n ** 0.5)) if std > 0 else None,
        "n_obs": n,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=60, help="сколько лучших прогонов считать копилкой")
    parser.add_argument("--all", action="store_true", help="посчитать копилку для всех строк")
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    with RESULTS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    ok_rows = [r for r in rows if r.get("status") == "OK"]
    print(f"строк всего: {len(rows)}, OK: {len(ok_rows)}")

    # Отбор: сначала по t (с учётом знака), затем по просадке.
    ok_rows.sort(key=lambda r: (-(r.get("t_stat") or -99), r.get("max_dd_pct") or 999))
    if not args.all:
        selected = ok_rows[: args.top]
    else:
        selected = ok_rows
    print(f"для копилки: {len(selected)} строк")

    btc = _btc_close()
    close_cache: dict[str, pd.Series] = {}

    out_rows: list[dict[str, Any]] = []
    for i, row in enumerate(selected, start=1):
        idx = row["idx"]
        npz_path = RETURNS / f"{idx:06d}.npz"
        if not npz_path.exists():
            continue
        returns = pd.Series(np.load(npz_path)["ret"].astype(float))
        symbol = row["symbol"]
        if symbol not in close_cache:
            try:
                close_cache[symbol] = _load_close(symbol)
            except Exception:
                close_cache[symbol] = pd.Series(dtype=float)
        asset_close = close_cache[symbol]
        if asset_close.empty:
            continue

        # Индекс времени: доходность без дат -> восстанавливаем из CSV символа.
        asset_index = asset_close.index
        n = len(returns)
        if len(asset_index) < n:
            continue
        idx_slice = asset_index[-n:]
        equity = (1.0 + returns.to_numpy()).cumprod()
        strategy_equity = pd.Series(equity * START_CAPITAL, index=idx_slice)

        kop = run_kopilka(strategy_equity, asset_close, btc)
        if kop.get("status") != "OK":
            continue
        base = _stats(returns)
        entry = {
            "idx": idx,
            "family": row["family"],
            "symbol": symbol,
            "risk": row["risk"],
            "params": row.get("params"),
            "base": {
                "annual_pct": base.get("annual_pct"),
                "max_dd_pct": base.get("max_dd_pct"),
                "t_stat": base.get("t_stat"),
                "final_value": None,
            },
            "kopilka": {
                "annual_pct": kop["annual_pct"],
                "max_dd_pct": kop["max_dd_pct"],
                "t_stat": kop["t_stat"],
                "final_value": kop["final_value"],
                "final_btc_units": kop["final_btc_units"],
                "final_btc_price": kop["final_btc_price"],
                "final_btc_value": kop["final_btc_value"],
                "final_asset_value": kop["final_asset_value"],
                "final_cash": kop["final_cash"],
                "btc_share_pct": kop["btc_share_pct"],
                "asset_share_pct": kop["asset_share_pct"],
                "locks": kop["locks"],
                "returns_to_asset": kop["returns_to_asset"],
            },
        }
        entry["delta_annual_pct"] = (
            kop["annual_pct"] - base["annual_pct"]
            if kop["annual_pct"] is not None and base.get("annual_pct") is not None else None
        )
        entry["delta_dd_pct"] = (
            kop["max_dd_pct"] - base["max_dd_pct"]
            if kop["max_dd_pct"] is not None and base.get("max_dd_pct") is not None else None
        )
        out_rows.append(entry)
        if i % 10 == 0:
            print(f"  {i}/{len(selected)}", flush=True)

    payload = {
        "date": "2026-10-25",
        "period": {"start": "2021-10-20", "end": "2026-10-19", "years": 5},
        "declared_parameters": {
            "lock_threshold": LOCK_THRESHOLD,
            "lock_share_of_gain": LOCK_SHARE,
            "return_share_of_btc": RETURN_SHARE,
            "drawdown_trigger": DRAWDOWN_TRIGGER,
            "ma_window": MA_WINDOW,
            "cost_per_leg": COST,
            "start_capital": START_CAPITAL,
        },
        "n_selected": len(selected),
        "n_computed": len(out_rows),
        "honest_limits": [
            "Наложение применяется к реализованной дневной доходности стратегии, а не к повторному прогону движка со смешанным BTC-рукавом.",
            "Отбор кандидатов сделан на том же 5-летнем окне, которое идёт в скан: поздний срез не является неприкосновенной проверкой.",
            "Комиссия движка уже учтена в доходности стратегии; в копилке считается только комиссия переводов (10 bps на ногу).",
            "Цены актива и BTC — из локальных биржевых CSV, тот же источник, что и доходность.",
        ],
        "rows": out_rows,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nwritten: {OUT}  ({len(out_rows)} строк)")


if __name__ == "__main__":
    main()
