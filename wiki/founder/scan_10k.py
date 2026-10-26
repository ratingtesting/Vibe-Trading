"""Scan 10k block 1: 67 archetype variants x 3 risk overlays x 30 pairs = 6030 runs.

Founder's directive (2026-10-23, repeated 5+ times): run 10 000+ strategies
taken from reference repos / scientific sources / this repo. Crypto first.
This is block 1 of the 3-block manifest (~13 230 runs total, ~$0 CPU):

  block 1 (this):  67 variants x 3 risk regimes x 30 pairs = 6 030
  block 2:         Alpha Zoo alive factors x 30 pairs x 2 horizons (separate)
  block 3:         freqtrade rules x 30 pairs (separate)

Risk regimes applied INSIDE the scan (the founder: «работать с просадкой,
рисками, стоплоссами»):
  raw          - the variant as-is
  vol10        - VolTargeted(target_vol=0.10)
  vol12dd820   - VolTargeted(0.12) + DrawdownThrottled(soft 8%, hard 20%)

Gate check afterwards: the founder's two-level bar (t>=3 reference,
t>=2.5 candidate, both DD<=20%).
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
from archetype_grid import VARIANTS  # noqa: E402
from archetypes.signal_engines import (  # noqa: E402
    DrawdownThrottled,
    MARegimeFilter,
    RegimeSwitching,
    TSMOM,
    VolTargeted,
    VolatilityBreakout,
    ZScoreMeanReversion,
)
from research_metrics import (  # noqa: E402
    metrics_from_returns,
    passes_drawdown_gate,
)

REPO = Path(__file__).resolve().parents[2]
PANEL = REPO / "data" / "founder-crypto-panel.pkl"
OUT = Path(__file__).resolve().parent / "scan-10k"
RESULTS_PATH = OUT / "scan-results.json"
TOP_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
    "XRPUSDT", "LTCUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT",
    "TRXUSDT", "BCHUSDT", "ATOMUSDT", "ETCUSDT", "XLMUSDT",
    "AVAXUSDT", "DASHUSDT", "NEOUSDT", "ZECUSDT", "QTUMUSDT",
    "ALGOUSDT", "VETUSDT", "HOTUSDT", "ZILUSDT", "MANAUSDT",
    "ENJUSDT", "IOTXUSDT", "CFXUSDT", "ONTUSDT", "THETAUSDT",
]

# SECURITY NOTE ON PICKLE
# Same trust boundary as run_alpha_zoo_crypto.py: the panel is written by
# build_crypto_panel.py in this same repo from the founder's own Binance CSVs.
# Not untrusted input.


def _risk_engines(family: str, params: dict[str, Any]) -> list[tuple[str, Any]]:
    base_cls = {
        "TSMOM": TSMOM, "MARegimeFilter": MARegimeFilter,
        "VolatilityBreakout": VolatilityBreakout, "ZScoreMeanReversion": ZScoreMeanReversion,
        "RegimeSwitching": RegimeSwitching,
    }[family]
    base = base_cls(**params)
    return [
        ("raw", base),
        ("vol10", VolTargeted(base, target_vol=0.10)),
        ("vol12dd820", DrawdownThrottled(VolTargeted(base, target_vol=0.12), soft_dd=0.08, hard_dd=0.20)),
    ]


def _equity_series(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    return frame.set_index("timestamp")["equity"]


def _sharpe(returns: pd.Series) -> float | None:
    m = metrics_from_returns(returns)
    return m.sharpe_annual


def _t_stat(returns: pd.Series) -> float | None:
    m = metrics_from_returns(returns)
    return m.t_stat


def main() -> None:
    variants: list[tuple[str, dict[str, Any]]] = [
        (family, params) for family, plist in VARIANTS.items() for params in plist
    ]
    total = len(variants) * 3 * len(TOP_SYMBOLS)
    print(f"scan-10k block 1: {len(variants)} variants x 3 risk x {len(TOP_SYMBOLS)} pairs = {total} runs")

    loader = LocalLoader()
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    results: list[dict[str, Any]] = []
    index = 0

    for family, params in variants:
        for symbol in TOP_SYMBOLS:
            for risk_name, engine in _risk_engines(family, params):
                index += 1
                run_dir = OUT / f"{family}-{risk_name}-{index}"
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
                    results.append({"family": family, "risk": risk_name, "symbol": symbol,
                                    "status": "ERROR", "error": str(exc)[:160]})
                    continue
                equity = _equity_series(run_dir)
                returns = equity.pct_change().dropna() if len(equity) > 2 else pd.Series(dtype=float)
                m = metrics_from_returns(returns)
                results.append({
                    "family": family, "risk": risk_name, "symbol": symbol, "status": "OK",
                    "annual_pct": m.annual_pct if m.annual_pct is not None else float(result.get("annual_return") or 0.0) * 100,
                    "max_dd_pct": -abs(m.max_dd_pct) if m.max_dd_pct is not None else float(result.get("max_drawdown") or 0.0) * 100,
                    "sharpe_annual": m.sharpe_annual,
                    "sharpe_per_observation": m.sharpe_per_observation,
                    "t_stat": m.t_stat,
                    "skew": m.skew,
                    "kurtosis": m.kurtosis,
                    "n_obs": m.n_obs,
                    "trade_count": int(result.get("trade_count") or 0),
                })
                if index % 250 == 0:
                    elapsed = time.time() - started
                    print(f"  {index}/{total} ({elapsed:.0f}s, {index/elapsed:.2f} runs/s)", flush=True)
                    # incremental save so progress survives a kill
                    RESULTS_PATH.write_text(json.dumps({"results": results}, indent=1, ensure_ascii=False),
                                            encoding="utf-8")

    RESULTS_PATH.write_text(json.dumps({"results": results}, indent=1, ensure_ascii=False),
                            encoding="utf-8")
    ok = [r for r in results if r.get("status") == "OK"]
    # Просадка в артефактах отрицательная: «не хуже 20%» это |dd| <= 20.
    # Раньше стояло `(max_dd_pct) <= 20` — при отрицательной просадке это
    # проходило ЛЮБОЕ отрицательное число, включая -90%.
    # DSR здесь НЕ считается: дефляция требует весь пул испытаний и
    # разброс Sharpe по нему. Это делает honest_dsr_recheck.py по уже
    # записанным equity.csv, где пул известен целиком.
    g4 = [r for r in ok if r.get("t_stat") is not None and abs(r["t_stat"]) >= 3.0
          and passes_drawdown_gate(r.get("max_dd_pct"), 20.0)]
    cand = [r for r in ok if r.get("t_stat") is not None and abs(r["t_stat"]) >= 2.5
            and passes_drawdown_gate(r.get("max_dd_pct"), 20.0)]
    print("\n=== SCAN-10K BLOCK 1 ИТОГ ===")
    print(f"прогонов: {len(results)} OK={len(ok)} время {time.time()-started:.0f}s")
    print(f"G4 (t>=3 AND |DD|<=20%): {len(g4)} | CANDIDATE (t>=2.5 AND |DD|<=20%): {len(cand)}")
    print("NB: без DSR. Дефляция считается отдельным проходом по всему пулу (honest_dsr_recheck.py).")
    cand.sort(key=lambda r: -(r.get("t_stat") or 0))
    for r in cand[:15]:
        print(f"  {r['family']}-{r['risk']} {r['symbol']}: {r['annual_pct']:+.2f}%/год t={r['t_stat']:.3f} DD={r['max_dd_pct']:.1f}%")
    print(f"written: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
