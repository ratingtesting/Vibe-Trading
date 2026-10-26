"""BTC-копилка: сравнение 13 кандидатов БЕЗ и С дополнением владельца.

ИДЕЯ ВЛАДЕЛЬЦА (сохраняется без подмены):
  1. Когда счёт вырос на 30-50% от зафиксированной точки отсчёта,
     50-75% именно этого ПРИРОСТА переводится в BTC.
  2. BTC — накопительный защитный актив, он не продаётся «просто так».
  3. Когда по исходному активу подтверждено прохождение дна, 30% BTC-резерва
     возвращается в исходный актив.

ЧТО ЗДЕСЬ ЧЕСТНО:
  * Капитал и единицы явные: стратегический юнит, BTC-юнит, кэш.
  * Комиссия 10 bps на каждую ногу перевода списывается из счёта.
  * Правило подтверждения дна — причинное (past-only): закрытие исходного
    актива выше его собственной 50-дневной скользящей средней, и только
    после просадки счёта не менее 10% от пика. Будущие значения не читаются.
  * Наложение применяется к РЕАЛИЗОВАННОЙ дневной доходности стратегии
    (artifacts/equity.csv). Это честная аппроксимация «сигнал + BTC-рукав»,
    а не повторный прогон движка со смешанным портфелем. Оговорка выводится
    в результат.

ЗАДЕКЛАРИРОВАННЫЕ ПАРАМЕТРЫ (меняются только новой версией файла):
  LOCK_THRESHOLD = 0.30   — порог фиксации прироста (30%)
  LOCK_SHARE     = 0.75   — доля прироста, уходящая в BTC (75%)
  RETURN_SHARE   = 0.30   — доля BTC-резерва, возвращаемая в актив (30%)
  DRAWDOWN_TRIGGER = 0.10 — просадка счёта от пика, после которой ищем дно
  MA_WINDOW      = 50     — окно средней для подтверждения дна
  COST           = 0.001  — 10 bps на ногу
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
CANDIDATES_CSV = REPO / "wiki" / "audit" / "LEGACY_13_CANDIDATES.csv"
BTC_CSV = REPO / "data" / "binance-spot-1d" / "BTCUSDT.csv"
OUT = REPO / "wiki" / "audit" / "BTC_KOPILKA_13.json"

LOCK_THRESHOLD = 0.30
LOCK_SHARE = 0.75
RETURN_SHARE = 0.30
DRAWDOWN_TRIGGER = 0.10
MA_WINDOW = 50
COST = 0.001
START_CAPITAL = 100.0

# Чувствительность: владелец назвал диапазоны (рост 30-50%, доля прироста
# 50-75%). Перебираем их и вариант «не возвращать BTC в актив».
THRESHOLD_GRID = (0.30, 0.50)
SHARE_GRID = (0.50, 0.75)
RETURN_GRID = (0.00, 0.30)


# ---------------------------------------------------------------- data loading


def _read_equity(run_dir: Path) -> pd.DataFrame:
    path = run_dir / "artifacts" / "equity.csv"
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
    return frame[["timestamp", "ret"]].reset_index(drop=True)


def _read_symbol_close(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "ohlcv_{symbol}.csv"
    candidates = sorted(run_dir.glob("artifacts/ohlcv_*.csv"))
    if not candidates:
        return pd.Series(dtype=float)
    frame = pd.read_csv(candidates[0])
    date_col = "trade_date" if "trade_date" in frame.columns else "date"
    frame[date_col] = pd.to_datetime(frame[date_col])
    series = frame.set_index(date_col)["close"].astype(float)
    return series[~series.index.duplicated(keep="last")].sort_index()


def _btc_close() -> pd.Series:
    frame = pd.read_csv(BTC_CSV)
    frame["date"] = pd.to_datetime(frame["date"])
    series = frame.set_index("date")["close"].astype(float)
    return series[~series.index.duplicated(keep="last")].sort_index()


def _candidates() -> list[dict[str, object]]:
    import csv

    rows = list(csv.DictReader(CANDIDATES_CSV.open(encoding="utf-8-sig")))
    for row in rows:
        scan = "risk-overlay" if row["id"].endswith(("ddthrottle-16", "ddthrottle-36", "ddthrottle-40", "ddthrottle-28")) else "archetype-scan"
        row["scan"] = scan
    return rows


# ------------------------------------------------------------------- metrics


def _stats(daily: pd.Series) -> dict[str, float]:
    clean = daily.dropna()
    if len(clean) < 2:
        return {"annual_pct": 0.0, "max_dd_pct": 0.0, "t_stat": 0.0, "days": int(len(clean))}
    equity = (1.0 + clean).cumprod()
    drawdown = float((equity / equity.cummax() - 1.0).min())
    annual = float((1.0 + clean).prod() ** (365.0 / len(clean)) - 1.0)
    std = float(clean.std(ddof=1))
    t_stat = float(clean.mean() / std * (len(clean) ** 0.5)) if std > 0 else 0.0
    return {
        "annual_pct": annual * 100.0,
        "max_dd_pct": drawdown * 100.0,
        "t_stat": t_stat,
        "days": int(len(clean)),
    }


def _baseline(returns: pd.Series) -> tuple[pd.Series, dict[str, float]]:
    """Стратегия целиком в счёте: индекс единиц на каждый вложенный доллар."""
    units = (1.0 + returns.fillna(0.0)).cumprod()
    equity = START_CAPITAL * units
    daily = equity.pct_change().dropna()
    return equity, _stats(daily)


# -------------------------------------------------------------------- overlay


def run_overlay(
    strategy_equity: pd.Series,
    asset_close: pd.Series,
    btc_close: pd.Series,
    lock_threshold: float = LOCK_THRESHOLD,
    lock_share: float = LOCK_SHARE,
    return_share: float = RETURN_SHARE,
) -> dict[str, object]:
    """BTC-копилка поверх реализованной доходности стратегии.

    Счёт состоит из: стратегических юнитов (цена юнита = индекс стратегии),
    BTC-юнитов (цена = BTC) и кэша. Все переводы проходят через кэш с
    комиссией 10 bps на ногу.
    """
    idx = strategy_equity.index.intersection(btc_close.index)
    idx = idx.intersection(asset_close.index)
    if len(idx) < 60:
        return {"status": "SKIPPED", "reason": "insufficient overlapping data"}

    unit_price = strategy_equity.reindex(idx).astype(float)          # индекс стратегии
    btc_price = btc_close.reindex(idx).ffill().astype(float)
    asset_price = asset_close.reindex(idx).ffill().astype(float)

    asset_ma = asset_price.rolling(MA_WINDOW, min_periods=MA_WINDOW).mean()

    # Старт: весь счёт в стратегии (юниты по индексу стратегии).
    cash = 0.0
    strategy_units = START_CAPITAL / float(unit_price.loc[idx[0]])
    btc_units = 0.0
    lock_reference = START_CAPITAL
    peak_value = START_CAPITAL
    trough_value = START_CAPITAL
    episode_returned = False

    equity_curve: list[float] = []
    events: list[dict[str, object]] = []
    locks = 0
    returns_done = 0

    for date in idx:
        sp = float(unit_price.loc[date])
        bp = float(btc_price.loc[date])
        strategy_value = strategy_units * sp
        btc_value = btc_units * bp
        total = strategy_value + btc_value + cash

        # --- правило 1: фиксация прироста в BTC -------------------------------
        if strategy_value >= lock_reference * (1.0 + lock_threshold) and strategy_value > 0:
            gain = strategy_value - lock_reference
            move = lock_share * gain
            fee = move * COST
            # продаём юниты стратегии, кладём выручку минус комиссия в кэш
            units_sold = move / sp
            strategy_units -= units_sold
            cash += move - fee
            # покупаем BTC на кэш (комиссия второй ноги)
            btc_gross = cash / (1.0 + COST)
            btc_fee = btc_gross * COST
            btc_units += btc_gross / bp
            cash -= btc_gross + btc_fee
            lock_reference = strategy_units * sp
            locks += 1
            events.append({
                "date": str(date.date()),
                "event": "lock_to_btc",
                "moved_usd": round(move, 4),
                "fee_usd": round(fee + btc_fee, 4),
                "btc_units": round(btc_units, 8),
            })

        # --- правило 2: возврат 30% резерва в актив при подтверждённом дне ----
        drawdown = (total / peak_value - 1.0) if peak_value > 0 else 0.0
        trough_value = min(trough_value, total)
        ma_value = asset_ma.loc[date]
        # «Дно пройдено» = откат от пика >= триггера, восстановление >= половины
        # глубины просадки от дна И цена выше собственной 50-дневной средней.
        depth = peak_value - trough_value
        recovery = (total - trough_value) / depth if depth > 0 else 0.0
        confirmed = (
            not episode_returned
            and drawdown <= -DRAWDOWN_TRIGGER
            and recovery >= 0.5
            and pd.notna(ma_value)
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
            events.append({
                "date": str(date.date()),
                "event": "return_to_asset",
                "recovery_ratio": round(recovery, 3),
                "sold_btc_units": round(sell_units, 8),
                "fee_usd": round(fee, 4),
                "bought_strategy_units": round(units_bought, 6),
            })

        strategy_value = strategy_units * sp
        btc_value = btc_units * bp
        total = strategy_value + btc_value + cash
        equity_curve.append(total)
        if total > peak_value:
            # новый максимум — новая эпизодная ветка для правила возврата
            peak_value = total
            trough_value = total
            episode_returned = False

    equity = pd.Series(equity_curve, index=idx)
    daily = equity.pct_change().dropna()
    stats = _stats(daily)
    final_btc_units = float(btc_units)
    final_btc_price = float(btc_price.loc[idx[-1]])
    return {
        "status": "OK",
        "equity": equity,
        "stats": stats,
        "final_value": float(equity.iloc[-1]),
        "final_btc_units": final_btc_units,
        "final_btc_price": final_btc_price,
        "final_btc_value": final_btc_units * final_btc_price,
        "final_strategy_value": float(strategy_units * float(unit_price.loc[idx[-1]])),
        "final_cash": float(cash),
        "locks": locks,
        "returns_to_asset": returns_done,
        "events": events,
    }


# ----------------------------------------------------------------------- main


def main() -> None:
    btc = _btc_close()
    results: list[dict[str, object]] = []
    sensitivity: list[dict[str, object]] = []

    for row in _candidates():
        run_dir = FOUNDER / str(row["scan"]) / str(row["id"])
        if not (run_dir / "artifacts" / "equity.csv").exists():
            results.append({"id": row["id"], "status": "MISSING_RUN_DIR"})
            continue
        equity_frame = _read_equity(run_dir)
        returns = equity_frame.set_index("timestamp")["ret"]
        base_equity, base_stats = _baseline(returns)
        asset_close = _read_symbol_close(run_dir)
        overlay = run_overlay(base_equity, asset_close, btc)

        entry: dict[str, object] = {
            "id": row["id"],
            "symbol": row["symbol"],
            "scan": row["scan"],
            "parameters": row["parameters"],
            "risk_parameters": row["risk_parameters"],
            "period_start": str(base_equity.index[0].date()),
            "period_end": str(base_equity.index[-1].date()),
            "baseline": base_stats,
            "baseline_final_value": float(base_equity.iloc[-1]),
        }
        if overlay.get("status") != "OK":
            entry["overlay"] = overlay
            results.append(entry)
            continue
        over_stats = overlay["stats"]
        entry["overlay"] = {
            "annual_pct": over_stats["annual_pct"],
            "max_dd_pct": over_stats["max_dd_pct"],
            "t_stat": over_stats["t_stat"],
            "final_value": overlay["final_value"],
            "final_btc_units": overlay["final_btc_units"],
            "final_btc_price": overlay["final_btc_price"],
            "final_btc_value": overlay["final_btc_value"],
            "final_strategy_value": overlay["final_strategy_value"],
            "final_cash": overlay["final_cash"],
            "locks": overlay["locks"],
            "returns_to_asset": overlay["returns_to_asset"],
            "btc_share_pct": (
                overlay["final_btc_value"] / overlay["final_value"] * 100.0
                if overlay["final_value"] > 0 else 0.0
            ),
            "delta_annual_pct": over_stats["annual_pct"] - base_stats["annual_pct"],
            "delta_dd_pct": over_stats["max_dd_pct"] - base_stats["max_dd_pct"],
            "delta_final_value": overlay["final_value"] - float(base_equity.iloc[-1]),
            "events": overlay["events"],
        }
        results.append(entry)

        # чувствительность параметров, названных владельцем
        for threshold in THRESHOLD_GRID:
            for share in SHARE_GRID:
                for ret_share in RETURN_GRID:
                    variant = run_overlay(
                        base_equity, asset_close, btc,
                        lock_threshold=threshold, lock_share=share, return_share=ret_share,
                    )
                    if variant.get("status") != "OK":
                        continue
                    vstats = variant["stats"]
                    sensitivity.append({
                        "id": row["id"],
                        "lock_threshold": threshold,
                        "lock_share": share,
                        "return_share": ret_share,
                        "annual_pct": vstats["annual_pct"],
                        "max_dd_pct": vstats["max_dd_pct"],
                        "final_value": variant["final_value"],
                        "final_btc_units": variant["final_btc_units"],
                        "btc_share_pct": (
                            variant["final_btc_value"] / variant["final_value"] * 100.0
                            if variant["final_value"] > 0 else 0.0
                        ),
                        "delta_annual_pct": vstats["annual_pct"] - base_stats["annual_pct"],
                        "delta_dd_pct": vstats["max_dd_pct"] - base_stats["max_dd_pct"],
                    })

    payload = {
        "date": "2026-10-24",
        "declared_parameters": {
            "lock_threshold": LOCK_THRESHOLD,
            "lock_share_of_gain": LOCK_SHARE,
            "return_share_of_btc": RETURN_SHARE,
            "drawdown_trigger": DRAWDOWN_TRIGGER,
            "ma_window": MA_WINDOW,
            "cost_per_leg": COST,
            "start_capital": START_CAPITAL,
        },
        "n_candidates": len(results),
        "n_completed": len([r for r in results if isinstance(r.get("overlay"), dict) and "annual_pct" in r["overlay"]]),
        "sensitivity": sensitivity,
        "honest_limits": [
            "Наложение применяется к реализованной дневной доходности стратегии, а не к повторному прогону движка со смешанным BTC-рукавом.",
            "Отбор 13 кандидатов сделан на полном периоде: поздний срез не является неприкосновенной проверкой.",
            "Четыре кандидата с ddthrottle построены на position_adjustment='hold': их просадка завышена, строки помечены.",
            "Комиссия 10 bps на ногу, спред и проскальзывание взяты из уже применённой в движке модели; в оверлее учтены только переводы.",
        ],
        "results": results,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"=== BTC-КОПИЛКА: {len(results)} кандидатов ===")
    print(f"{'ID':38} {'база %/год':>10} {'BTC %/год':>10} {'DD база':>8} {'DD BTC':>8} {'$ финал':>9} {'BTC, шт':>12} {'доля %':>7}")
    for row in results:
        overlay = row.get("overlay")
        if not isinstance(overlay, dict) or "annual_pct" not in overlay:
            print(f"{row['id']:38} {overlay if overlay else row.get('status','?')}")
            continue
        base = row["baseline"]
        print(
            f"{row['id']:38} {base['annual_pct']:>10.2f} {overlay['annual_pct']:>10.2f} "
            f"{base['max_dd_pct']:>8.2f} {overlay['max_dd_pct']:>8.2f} "
            f"{overlay['final_value']:>9.2f} {overlay['final_btc_units']:>12.6f} {overlay['btc_share_pct']:>7.2f}"
        )
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
