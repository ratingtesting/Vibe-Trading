"""Freqtrade block: 21 community rules x 30 pairs x 2 risk modes = 1260 runs.

Same harness as scan_10k.py (CryptoEngine + LocalLoader, 2020-01-01..2026-10-19,
leverage 1.0, costs inside the engine). Results schema identical: family/risk/
symbol/status/annual_pct/max_dd_pct/sharpe/t_stat/trade_count. Incremental save
every 250 runs. Founder's bar: REFERENCE t>=3 AND DD<=20 (max_dd_pct >= -20);
CANDIDATE t 2.5-3 AND DD<=20.

DSR НЕ считается здесь намеренно: дефляция требует знать ВЕСЬ пул
испытаний и разброс Sharpe по нему, а прогон идёт по одному блоку. DSR
считается отдельным проходом (honest_dsr_recheck.py) по уже записанным
equity.csv — там, где пул известен целиком. Здесь же фиксируются
периодический Sharpe и реальные моменты, из которых тот проход берёт DSR.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "archetypes"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest.engines.crypto import CryptoEngine  # noqa: E402
from backtest.loaders.local_loader import DataLoader as LocalLoader  # noqa: E402
from freqtrade_engines import RULES, FreqRuleEngine  # noqa: E402
from archetypes.signal_engines import VolTargeted  # noqa: E402
from research_metrics import (  # noqa: E402
    metrics_from_returns,
    passes_drawdown_gate,
    sharpe_per_observation,
)

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "freqtrade-scan"
RESULTS_PATH = OUT / "scan-results.json"

TOP_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
    "XRPUSDT", "LTCUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT",
    "TRXUSDT", "BCHUSDT", "ATOMUSDT", "ETCUSDT", "XLMUSDT",
    "AVAXUSDT", "DASHUSDT", "NEOUSDT", "ZECUSDT", "QTUMUSDT",
    "ALGOUSDT", "VETUSDT", "HOTUSDT", "ZILUSDT", "MANAUSDT",
    "ENJUSDT", "IOTXUSDT", "CFXUSDT", "ONTUSDT", "THETAUSDT",
]


def _risk_engines(rule: str) -> list[tuple[str, Any]]:
    base = FreqRuleEngine(rule)
    return [("raw", base), ("vol10", VolTargeted(base, target_vol=0.10))]


def _equity_series(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    return frame.set_index("timestamp")["equity"]


def _sharpe(returns: pd.Series) -> float | None:
    return sharpe_per_observation(returns)


def _t_stat(returns: pd.Series) -> float | None:
    return metrics_from_returns(returns).t_stat


def main() -> None:
    total = len(RULES) * 2 * len(TOP_SYMBOLS)
    print(f"freqtrade block: {len(RULES)} rules x 2 risk x {len(TOP_SYMBOLS)} pairs = {total} runs")

    loader = LocalLoader()
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    results: list[dict[str, Any]] = []
    index = 0

    for rule in RULES:
        for symbol in TOP_SYMBOLS:
            for risk_name, engine in _risk_engines(rule):
                index += 1
                run_dir = OUT / f"{rule}-{risk_name}-{index}"
                run_dir.mkdir(parents=True, exist_ok=True)
                config = {
                    "codes": [symbol], "source": "local",
                    "start_date": "2020-01-01", "end_date": "2026-10-19",
                    "initial_cash": 10_000.0, "leverage": 1.0,
                    "interval": "1D", "perpetual_strict": False,
                }
                try:
                    market = CryptoEngine(config)
                    result = market.run_backtest(config, loader, engine, run_dir, bars_per_year=365)
                except Exception as exc:  # noqa: BLE001 — record and continue
                    results.append({"family": rule, "risk": risk_name, "symbol": symbol,
                                    "status": "ERROR", "error": str(exc)[:160]})
                    continue
                equity = _equity_series(run_dir)
                returns = equity.pct_change().dropna() if len(equity) > 2 else pd.Series(dtype=float)
                m = metrics_from_returns(returns)
                results.append({
                    "family": rule, "risk": risk_name, "symbol": symbol, "status": "OK",
                    "annual_pct": m.annual_pct if m.annual_pct is not None else float(result.get("annual_return") or 0.0) * 100,
                    "max_dd_pct": -abs(m.max_dd_pct) if m.max_dd_pct is not None else float(result.get("max_drawdown") or 0.0) * 100,
                    "sharpe": m.sharpe_per_observation,
                    "sharpe_annual": m.sharpe_annual,
                    "t_stat": m.t_stat,
                    "skew": m.skew,
                    "kurtosis": m.kurtosis,
                    "n_obs": m.n_obs,
                    "trade_count": int(result.get("trade_count") or 0),
                })
                if index % 250 == 0:
                    elapsed = time.time() - started
                    print(f"  {index}/{total} ({elapsed:.0f}s)", flush=True)
                    RESULTS_PATH.write_text(json.dumps({"results": results}, indent=1, ensure_ascii=False),
                                            encoding="utf-8")

    RESULTS_PATH.write_text(json.dumps({"results": results}, indent=1, ensure_ascii=False),
                            encoding="utf-8")
    ok = [r for r in results if r.get("status") == "OK" and r["t_stat"] is not None]
    # Просадка в артефактах отрицательная: «не хуже 20%» это |dd| <= 20.
    ref = [r for r in ok if abs(r["t_stat"]) >= 3.0 and passes_drawdown_gate(r.get("max_dd_pct"), 20.0)]
    cand = [r for r in ok if 2.5 <= abs(r["t_stat"]) < 3.0 and passes_drawdown_gate(r.get("max_dd_pct"), 20.0)]
    print("\n=== FREQTRADE BLOCK ИТОГ ===")
    print(f"прогонов: {len(results)} OK={len(ok)} время {time.time()-started:.0f}s")
    print(f"REFERENCE (t>=3, DD<=20%): {len(ref)} | CANDIDATE (t 2.5-3, DD<=20%): {len(cand)}")
    print("NB: без DSR. Дефляция считается отдельным проходом по всему пулу (honest_dsr_recheck.py).")
    ref.sort(key=lambda r: -(r["annual_pct"] or 0))
    for r in ref[:10]:
        print(f"  {r['family']:14s} {r['risk']:5s} {r['symbol']:10s} {r['annual_pct']:+7.2f}%/год t={r['t_stat']:.3f} DD={r['max_dd_pct']:.1f}%")
    print(f"written: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
