"""13 кандидатов за 5 ЛЕТ + BTC-копилка: полный расклад счёта.

ЗАЧЕМ (владелец, 25.10.26)
«Прогон надо делать за 5 лет и каждый раз считать доходность в годовых...
Потом новых кандидатов прогнать дополнительно биткоин копилкой. Учесть,
сколько биткоина скопилось, сколько самого актива стало в долларах,
сколько совокупно актив + биткоин. В отчете только полные таблицы.»

То есть для каждого из 13 ТРЕБУЕТСЯ полная таблица:
  годовая доходность базы | годовая с копилкой | Δ | BTC в штуках |
  BTC в долларах | актив в долларах | кэш | ВСЕГО | доля BTC | фиксации

ЧТО ОТЛИЧАЕТСЯ ОТ ПРЕДЫДУЩИХ ПРОГОНОВ
- Период 5 лет (2021-10-20..2026-10-19), не 1 год и не вся история.
- Доходность в годовых из дневной доходности: (prod(1+r))^(365/n)-1.
- position_adjustment="rebalance" — исполняемое изменение размера.
- Копилка с теми же константами владельца (30% / 75% / 30%, комиссия 10 bps
  на ногу, причинное правило подтверждения дна).

ВЫХОД
wiki/founder/candidates-13-5y/kopilka-13-5y.json  — данные
wiki/founder/candidates-13-5y/report.md       — таблицы
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
OUT = FOUNDER / "candidates-13-5y"

sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(FOUNDER))
sys.path.insert(0, str(FOUNDER / "archetypes"))

from backtest.engines.crypto import CryptoEngine  # noqa: E402
from backtest.loaders.local_loader import DataLoader as LocalLoader  # noqa: E402
from research_metrics import metrics_from_returns  # noqa: E402
import kopilka_5y  # noqa: E402
import btc_kopilka_13 as legacy  # noqa: E402

from archetypes.signal_engines import (  # noqa: E402
    DrawdownThrottled,
    MARegimeFilter,
    RegimeSwitching,
    TSMOM,
)

START_DATE = "2021-10-20"
END_DATE = "2026-10-19"
START_CAPITAL = 100.0

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


def _engine_for(family: str, params: dict[str, Any], risk: str):
    base = FAMILIES[family](**params)
    if risk == "raw":
        return base
    if risk == "ddthrottle":
        return DrawdownThrottled(base, soft_dd=0.15, hard_dd=0.35)
    raise ValueError(risk)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    loader = LocalLoader()
    btc = kopilka_5y._btc_close()
    started = time.time()
    rows: list[dict[str, Any]] = []

    for cid, family, symbol, params, risk in CANDIDATES:
        run_dir = OUT / "runs" / cid
        run_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "codes": [symbol], "source": "local",
            "start_date": START_DATE, "end_date": END_DATE,
            "initial_cash": 10_000.0, "leverage": 1.0, "interval": "1D",
            "perpetual_strict": False, "position_adjustment": "rebalance",
        }
        market = CryptoEngine(config)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            metrics = market.run_backtest(
                config, loader, _engine_for(family, params, risk), run_dir,
                bars_per_year=365)

        frame = pd.read_csv(run_dir / "artifacts" / "equity.csv", parse_dates=["timestamp"])
        frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
        returns = frame.set_index("timestamp")["ret"].dropna().astype(float)
        m = metrics_from_returns(returns)

        # Даты для копилки: берём из CSV символа, он же источник цен.
        asset_close = kopilka_5y._load_close(symbol)
        idx = asset_close.index.intersection(pd.DatetimeIndex(frame["timestamp"]))
        if len(idx) < len(returns):
            # Символ старше стратегии — берём хвост той же длины.
            idx = pd.DatetimeIndex(frame["timestamp"])[-len(asset_close):]
        returns = returns.iloc[-len(idx):] if len(returns) >= len(idx) else returns
        equity = (1.0 + returns.to_numpy()).cumprod() * START_CAPITAL
        strategy_equity = pd.Series(equity, index=idx)

        kop = kopilka_5y.run_kopilka(strategy_equity, asset_close, btc)
        base_annual = m.annual_pct
        row: dict[str, Any] = {
            "id": cid, "family": family, "symbol": symbol,
            "parameters": params, "risk": risk,
            "period_start": START_DATE, "period_end": END_DATE,
            "base": {
                "annual_pct": base_annual,
                "max_dd_pct": m.max_dd_pct,
                "t_stat": m.t_stat,
                "sharpe_per_obs": m.sharpe_per_observation,
                "n_obs": m.n_obs,
                "trade_count": metrics.get("trade_count"),
                "dropped_target_adjustment_count": metrics.get("dropped_target_adjustment_count"),
            },
            "kopilka": kop if kop.get("status") == "OK" else {"status": kop.get("status")},
        }
        if kop.get("status") == "OK":
            row["delta_annual_pct"] = kop["annual_pct"] - base_annual
            row["delta_dd_pct"] = kop["max_dd_pct"] - m.max_dd_pct
        rows.append(row)
        kop_part = (f"{kop['annual_pct']:.2f}%" if kop.get("status") == "OK" else "—")
        print(f"  {cid:38s} база {base_annual or 0:+7.2f}%/год t={m.t_stat or 0:.3f} "
              f"DD={m.max_dd_pct or 0:6.2f}% | копилка {kop_part}", flush=True)

    payload = {
        "date": "2026-10-25",
        "period": {"start": START_DATE, "end": END_DATE, "years": 5},
        "position_adjustment": "rebalance",
        "start_capital": START_CAPITAL,
        "declared_parameters": {
            "lock_threshold": kopilka_5y.LOCK_THRESHOLD,
            "lock_share_of_gain": kopilka_5y.LOCK_SHARE,
            "return_share_of_btc": kopilka_5y.RETURN_SHARE,
            "drawdown_trigger": kopilka_5y.DRAWDOWN_TRIGGER,
            "ma_window": kopilka_5y.MA_WINDOW,
            "cost_per_leg": kopilka_5y.COST,
        },
        "n_candidates": len(rows),
        "honest_limits": [
            "Период 5 лет (2021-10-20..2026-10-19) одинаков для всех 13 — сопоставимо.",
            "Выбор 13 сделан на полной истории 2020-2026: этот срез НЕ является независимой проверкой.",
            "Наложение копилки — к реализованной дневной доходности стратегии, а не повторный прогон движка со смешанным BTC-рукавом.",
            "Комиссия движка уже учтена в доходности; в копилке — только комиссия переводов 10 bps на ногу.",
        ],
        "rows": rows,
    }
    (OUT / "kopilka-13-5y.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    # --- Таблицы ---------------------------------------------------------
    def base_cell(row: dict[str, Any], key: str, fmt: str = ".2f") -> str:
        value = row["base"].get(key)
        return format(value, fmt) if isinstance(value, (int, float)) else "—"

    table_rows = []
    for row in rows:
        k = row["kopilka"]
        if k.get("status") == "OK":
            table_rows.append([
                row["id"], row["symbol"], row["risk"],
                base_cell(row, "annual_pct"), f"{k['annual_pct']:.2f}",
                f"{row['delta_annual_pct']:+.2f}",
                base_cell(row, "max_dd_pct"), f"{k['max_dd_pct']:.2f}",
                f"{row['delta_dd_pct']:+.2f}",
                f"{k['final_btc_units']:.6f}", f"{k['final_btc_value']:.2f}",
                f"{k['final_asset_value']:.2f}", f"{k['final_cash']:.2f}",
                f"{k['final_value']:.2f}", f"{k['btc_share_pct']:.1f}",
                str(k["locks"]), str(k["returns_to_asset"]),
            ])
        else:
            table_rows.append([row["id"], row["symbol"], row["risk"],
                               base_cell(row, "annual_pct"), "—", "—",
                               base_cell(row, "max_dd_pct"), "—", "—",
                               "—", "—", "—", "—", "—", "—", "—", "—"])

    report = [
        "# 13 кандидатов за 5 лет: база против BTC-копилки",
        "",
        f"Окно: {START_DATE} .. {END_DATE} (5 лет, 1826 дневных баров). "
        f"Стартовый капитал копилки: ${START_CAPITAL:.0f}. "
        "Доходность в годовых = (prod(1+r))^(365/n)-1.",
        "",
        "## 1. Полная таблица: доходность, риск и расклад счёта",
        "",
        _table(
            ["#", "ID", "Пара", "Риск", "База %/год", "С копилкой %/год", "Δ годовой",
             "База DD %", "DD с копилкой %", "Δ DD",
             "BTC накоплено, шт", "BTC в $", "Актив в $", "Кэш в $", "ВСЕГО в $",
             "Доля BTC %", "Фиксаций", "Возвратов"],
            [[str(i)] + r for i, r in enumerate(table_rows, start=1)]),
        "",
        "## 2. Параметры прогонов",
        "",
        _table(
            ["ID", "Семейство", "Параметры", "Риск-режим", "Наблюдений", "Сделки",
             "Отброшено ресайзов"],
            [[row["id"], row["family"],
              ", ".join(f"{k}={v}" for k, v in sorted(row["parameters"].items())),
              row["risk"], str(row["base"]["n_obs"]),
              str(row["base"].get("trade_count")),
              str(row["base"].get("dropped_target_adjustment_count"))]
             for row in rows]),
        "",
        "## 3. Итоги по копилке",
        "",
    ]
    ok_kop = [r for r in rows if r["kopilka"].get("status") == "OK"]
    improved = [r for r in ok_kop if (r.get("delta_annual_pct") or 0) > 0]
    worse_dd = [r for r in ok_kop if (r.get("delta_dd_pct") or 0) > 0]
    report.append(_table(
        ["Показатель", "Значение"],
        [
            ["Кандидатов прогнано", str(len(rows))],
            ["Копилка посчитана", str(len(ok_kop))],
            ["Копилка улучшила годовую доходность", f"{len(improved)} из {len(ok_kop)}"],
            ["Копилка ухудшила просадку (п.п.)", f"{len(worse_dd)} из {len(ok_kop)}"],
            ["Всего фиксаций (переводов в BTC)",
             str(sum(r["kopilka"]["locks"] for r in ok_kop))],
            ["Всего возвратов резерва в актив",
             str(sum(r["kopilka"]["returns_to_asset"] for r in ok_kop))],
            ["Максимум BTC накоплено, шт",
             f"{max((r['kopilka']['final_btc_units'] for r in ok_kop), default=0):.6f}"],
            ["Параметры копилки",
             f"порог {kopilka_5y.LOCK_THRESHOLD}, доля {kopilka_5y.LOCK_SHARE}, "
             f"возврат {kopilka_5y.RETURN_SHARE}, комиссия {kopilka_5y.COST} на ногу"],
        ]))
    report.append("\n## 4. Оговорки\n")
    report.append(_table(
        ["#", "Оговорка"],
        [[str(i), t] for i, t in enumerate(payload["honest_limits"], start=1)]))
    report.append("")

    (OUT / "report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"\nwritten: {OUT / 'report.md'}")
    print(f"written: {OUT / 'kopilka-13-5y.json'}  ({time.time()-started:.0f}s)")


if __name__ == "__main__":
    main()
