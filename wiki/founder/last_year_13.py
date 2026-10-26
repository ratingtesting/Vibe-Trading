"""13 кандидатов за ПОСЛЕДНИЙ ГОД + BTC-копилка, с честным исполнением размера.

ЗАЧЕМ ЭТОТ ФАЙЛ
Три предыдущих блока работали на полном периоде 2020-01-01..2026-10-19.
Последний год — это отдельный, более поздний срез: он отвечает на вопрос
«что стратегии делают СЕЙЧАС», а не «что они сделали за весь криптоцикл».

ЧТО ИСПРАВЛЕНО ПО СРАВНЕНИЮ С ПРЕДЫДУЩИМИ ПРОГОНАМИ

1. position_adjustment="rebalance". В режиме "hold" (дефолт) движок
   отбрасывает изменение РАЗМЕРА позиции в том же направлении:
   у roc10-vol10-AVAX было 2180 запросов изменения цели и 1885
   отброшенных — то есть плавающая позиция vol-оверлея почти не
   исполнялась, и колонка vol10 фактически показывала «raw с
   обрезанным входом». Здесь изменения размера исполняются.

2. Метрики берутся из research_metrics: периодный Sharpe, t со знаком,
   просадка как величина потери, реальные skew/kurtosis.

3. DSR здесь НЕ считается: дефляция требует знать весь пул испытаний.
   Этот прогон — один блок; дефляцию делает honest_dsr_recheck.py по
   всему пулу. Оговорка выводится в артефакт.

ЧТО СЧИТАЕТСЯ
Для каждого из 13 кандидатов: стратегия сама по себе и стратегия +
BTC-копилка (правила владельца: фиксация прироста в BTC, возврат
резерва при подтверждённом дне). Плюс параметры копилки по сетке
владельца. Стартовый капитал стратегии — тот же, что в прошлых
прогонах ($10 000 движка), копилка считается на $100 (как в 13-кандидатном
артефакте), чтобы числа сопоставимы.

ЧЕСТНЫЕ ОГОВОРКИ (попадают в артефакт)
- Один год — слишком короткий срез для устойчивого t; результат показывает
  поведение, а не доказанный край.
- Выбор 13 кандидатов сделан на полном периоде: этот срез не является
  неприкосновенной проверкой.
- Копилка накладывается на реализованную доходность стратегии, а не
  перегоняет движок со смешанным BTC-рукавом.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OUT_DIR = FOUNDER / "last-year"

sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(FOUNDER))
sys.path.insert(0, str(FOUNDER / "archetypes"))

from backtest.engines.crypto import CryptoEngine  # noqa: E402
from backtest.loaders.local_loader import DataLoader as LocalLoader  # noqa: E402
from research_metrics import metrics_from_returns  # noqa: E402
import btc_kopilka_13 as kopilka  # noqa: E402

from archetypes.signal_engines import (  # noqa: E402
    DrawdownThrottled,
    MARegimeFilter,
    RegimeSwitching,
    TSMOM,
)

# Период: последние 12 месяцев относительно конца доступных данных.
END_DATE = "2026-10-19"
START_DATE = "2025-10-20"

# 13 кандидатов: (id, семейство, символ, параметры, риск-режим)
CANDIDATES: list[tuple[str, str, str, dict[str, Any], str]] = [
    ("TSMOM-154", "TSMOM", "SOLUSDT", {"lookback": 126}, "raw"),
    ("TSMOM-94", "TSMOM", "SOLUSDT", {"lookback": 30}, "raw"),
    ("RegimeSwitching-864", "RegimeSwitching", "ZILUSDT", {"regime_period": 50, "trend_lookback": 14}, "raw"),
    ("RegimeSwitching-935", "RegimeSwitching", "ADAUSDT", {"regime_period": 100, "trend_lookback": 30}, "raw"),
    ("MARegimeFilter-214", "MARegimeFilter", "SOLUSDT", {"ma_period": 50}, "raw"),
    ("RegimeSwitching-905", "RegimeSwitching", "ADAUSDT", {"regime_period": 100, "trend_lookback": 14}, "raw"),
    ("RegimeSwitching-875", "RegimeSwitching", "ADAUSDT", {"regime_period": 50, "trend_lookback": 30}, "raw"),
    ("TSMOM-4", "TSMOM", "SOLUSDT", {"lookback": 7}, "raw"),
    ("TSMOM-SOLUSDT-ddthrottle-16", "TSMOM", "SOLUSDT", {"lookback": 126}, "ddthrottle"),
    ("RegimeSwitching-993", "RegimeSwitching", "BNBUSDT", {"regime_period": 200, "trend_lookback": 30}, "raw"),
    ("RegimeSwitching-ADAUSDT-ddthrottle-36", "RegimeSwitching", "ADAUSDT", {"regime_period": 100, "trend_lookback": 14}, "ddthrottle"),
    ("RegimeSwitching-ADAUSDT-ddthrottle-40", "RegimeSwitching", "ADAUSDT", {"regime_period": 100, "trend_lookback": 30}, "ddthrottle"),
    ("RegimeSwitching-ADAUSDT-ddthrottle-28", "RegimeSwitching", "ADAUSDT", {"regime_period": 50, "trend_lookback": 14}, "ddthrottle"),
]

FAMILIES = {
    "TSMOM": TSMOM,
    "MARegimeFilter": MARegimeFilter,
    "RegimeSwitching": RegimeSwitching,
}

KOPILKA_START_CAPITAL = 100.0


def _engine_for(family: str, params: dict[str, Any], risk: str):
    base = FAMILIES[family](**params)
    if risk == "raw":
        return base
    if risk == "ddthrottle":
        return DrawdownThrottled(base, soft_dd=0.15, hard_dd=0.35)
    raise ValueError(f"unknown risk {risk}")


def _equity_returns(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
    return frame.set_index("timestamp")["ret"].dropna().astype(float)


def _stats_from_returns(returns: pd.Series) -> dict[str, Any]:
    m = metrics_from_returns(returns)
    return {
        "n_obs": m.n_obs,
        "annual_pct": m.annual_pct,
        "max_dd_pct": m.max_dd_pct,
        "t_stat": m.t_stat,
        "sharpe_per_obs": m.sharpe_per_observation,
        "sharpe_annual": m.sharpe_annual,
        "skew": m.skew,
        "kurtosis": m.kurtosis,
    }


def main() -> None:
    loader = LocalLoader()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    btc = kopilka._btc_close()
    started = time.time()
    results: list[dict[str, Any]] = []

    for index, (cid, family, symbol, params, risk) in enumerate(CANDIDATES, start=1):
        run_dir = OUT_DIR / cid
        run_dir.mkdir(parents=True, exist_ok=True)
        engine = _engine_for(family, params, risk)
        config = {
            "codes": [symbol], "source": "local",
            "start_date": START_DATE, "end_date": END_DATE,
            "initial_cash": 10_000.0, "leverage": 1.0,
            "interval": "1D", "perpetual_strict": False,
            # Изменение размера позиции исполняется: без этого vol/dd
            # оверлеи запрашивали размер, а движок его отбрасывал.
            "position_adjustment": "rebalance",
        }
        market = CryptoEngine(config)
        market.run_backtest(config, loader, engine, run_dir, bars_per_year=365)

        returns = _equity_returns(run_dir)
        base_stats = _stats_from_returns(returns)
        # Метрики движка лежат в run_card.json -> "metrics", а не в
        # возвращаемом объекте прогона.
        run_card = run_dir / "run_card.json"
        metrics: dict[str, Any] = {}
        if run_card.exists():
            card = json.loads(run_card.read_text(encoding="utf-8"))
            metrics = card.get("metrics", {}) or {}
        diagnostics = {
            "position_adjustment": metrics.get("position_adjustment"),
            "target_change_count": metrics.get("target_change_count"),
            "dropped_target_adjustment_count": metrics.get("dropped_target_adjustment_count"),
            "rebalance_executed_fills": metrics.get("rebalance_executed_fills"),
            "rebalance_executed_bars": metrics.get("rebalance_executed_bars"),
            "rebalance_realized_turnover": metrics.get("rebalance_realized_turnover"),
            "trade_count": metrics.get("trade_count"),
            "engine_annual_pct": (metrics.get("annual_return") or 0.0) * 100.0,
            "engine_max_dd_pct": (metrics.get("max_drawdown") or 0.0) * 100.0,
        }

        entry: dict[str, Any] = {
            "id": cid, "family": family, "symbol": symbol,
            "parameters": params, "risk": risk,
            "period_start": START_DATE, "period_end": END_DATE,
            "baseline": base_stats,
            "diagnostics": diagnostics,
        }

        # BTC-копилка поверх реализованной доходности.
        asset_close = kopilka._read_symbol_close(run_dir)
        equity = (1.0 + returns).cumprod()
        overlay = kopilka.run_overlay(
            equity * KOPILKA_START_CAPITAL, asset_close, btc,
            lock_threshold=kopilka.LOCK_THRESHOLD,
            lock_share=kopilka.LOCK_SHARE,
            return_share=kopilka.RETURN_SHARE,
        )
        if overlay.get("status") == "OK":
            ov = overlay["stats"]
            entry["overlay"] = {
                "annual_pct": ov["annual_pct"],
                "max_dd_pct": ov["max_dd_pct"],
                "t_stat": ov["t_stat"],
                "final_value": overlay["final_value"],
                "final_btc_units": overlay["final_btc_units"],
                "final_btc_price": overlay["final_btc_price"],
                "final_btc_value": overlay["final_btc_value"],
                "locks": overlay["locks"],
                "returns_to_asset": overlay["returns_to_asset"],
                "btc_share_pct": (
                    overlay["final_btc_value"] / overlay["final_value"] * 100.0
                    if overlay["final_value"] > 0 else 0.0
                ),
                "delta_annual_pct": ov["annual_pct"] - base_stats["annual_pct"],
                "delta_dd_pct": ov["max_dd_pct"] - base_stats["max_dd_pct"],
            }
        else:
            entry["overlay"] = {"status": overlay.get("status"), "reason": overlay.get("reason")}

        results.append(entry)
        print(
            f"  [{index}/{len(CANDIDATES)}] {cid:38s} "
            f"база {base_stats['annual_pct'] or 0:+7.2f}%/год "
            f"t={base_stats['t_stat'] or 0:.3f} DD={base_stats['max_dd_pct'] or 0:5.1f}% "
            f"| BTC {(entry['overlay'].get('annual_pct') or 0):+7.2f}%/год",
            flush=True,
        )

    payload = {
        "date": "2026-10-25",
        "period": {"start": START_DATE, "end": END_DATE, "days": 365},
        "n_candidates": len(results),
        "position_adjustment": "rebalance",
        "kopilka_start_capital": KOPILKA_START_CAPITAL,
        "declared_parameters": {
            "lock_threshold": kopilka.LOCK_THRESHOLD,
            "lock_share_of_gain": kopilka.LOCK_SHARE,
            "return_share_of_btc": kopilka.RETURN_SHARE,
            "drawdown_trigger": kopilka.DRAWDOWN_TRIGGER,
            "ma_window": kopilka.MA_WINDOW,
            "cost_per_leg": kopilka.COST,
            "start_capital": KOPILKA_START_CAPITAL,
        },
        "honest_limits": [
            "Год — короткий срез: результат показывает текущее поведение, а не доказанный край.",
            "Выбор 13 кандидатов сделан на полном периоде 2020-2026; этот срез не является неприкосновенной проверкой.",
            "DSR здесь не считается: дефляция требует весь пул испытаний (см. honest_dsr_recheck.py).",
            "BTC-копилка накладывается на реализованную дневную доходность стратегии, а не перегоняет движок со смешанным BTC-рукавом.",
            "Комиссия 10 bps на ногу перевода внутри копилки; издержки самой стратегии — по модели движка.",
        ],
        "results": results,
    }
    out_path = OUT_DIR / "last-year-13.json"
    out_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\n=== 13 КАНДИДАТОВ ЗА ПОСЛЕДНИЙ ГОД ({START_DATE}..{END_DATE}) ===")
    print(f"{'ID':38} {'база %/год':>10} {'t':>6} {'DD':>7} | {'BTC %/год':>10} {'t':>6} {'DD':>7} {'BTC, шт':>11} {'доля %':>7}")
    for row in results:
        b = row["baseline"]
        o = row["overlay"]
        if "annual_pct" not in o:
            print(f"{row['id']:38} {b['annual_pct'] or 0:>10.2f} {b['t_stat'] or 0:>6.3f} {b['max_dd_pct'] or 0:>7.1f} | {o.get('status')}")
            continue
        print(
            f"{row['id']:38} {b['annual_pct'] or 0:>10.2f} {b['t_stat'] or 0:>6.3f} {b['max_dd_pct'] or 0:>7.1f} | "
            f"{o['annual_pct']:>10.2f} {o['t_stat']:>6.3f} {o['max_dd_pct']:>7.1f} "
            f"{o['final_btc_units']:>11.6f} {o['btc_share_pct']:>7.1f}"
        )
    print(f"\nwritten: {out_path}  ({time.time()-started:.0f}s)")


if __name__ == "__main__":
    main()
