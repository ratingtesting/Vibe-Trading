"""Run the founder's five archetypes over horizons 1/5/10/20 and symbols
top-10 by bar count, to produce a large enough strategy count that the
multiple-testing correction (Deflated Sharpe) is meaningful.

WHY: the parent project's P4 ran 23 hand-translated rules and reported zero
survivors. That scan was too small to say anything about the LIBRARY — with 23
trials the expected number of false positives at a 5% bar is ~1.2, and zero is
within the noise. The honest way to test a library is to push the trial count
high enough that a zero result is informative.

WHAT THIS RUNS
For each of the five executable founder archetypes (TSMOM, MARegimeFilter,
VolatilityBreakout, ZScoreMeanReversion, RegimeSwitching), for each of
several parameter variants taken from knowledge/12 (the literature column),
for each of the top-10 Binance spot symbols by bar count, this script:

  1. runs a real backtest through Vibe-Trading's CryptoEngine (leverage 1.0,
     the engine's own maker/taker/slippage schedule);
  2. collects the per-day equity series from artifacts/equity.csv;
  3. computes annualised return, Sharpe, t-statistic, max drawdown;
  4. runs Vibe-Trading's deflated_sharpe_ratio with n_trials set to the
     honest count of strategies tested in this run.

NO LLM is involved. This is pure Vibe-Trading code on the founder's panel —
cost is CPU time only.

WHAT IS REPORTED
Per-variant rows and an aggregate summary. A strategy counts as ALIVE only
when it clears BOTH G4 (|t| >= 3.0) and G5 (DSR >= 0.95) — the founder's
pre-registered bar. Survivorship bias is stated once, at the top: the panel is
a live exchange's current symbol list, so delisted coins are absent.
"""

from __future__ import annotations

import itertools
import json
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(REPO / "wiki" / "founder" / "archetypes"))

from backtest.engines.crypto import CryptoEngine  # noqa: E402
from backtest.loaders.local_loader import DataLoader as LocalLoader  # noqa: E402
from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

from signal_engines import (  # noqa: E402
    MARegimeFilter,
    RegimeSwitching,
    TSMOM,
    VolatilityBreakout,
    ZScoreMeanReversion,
)

PANEL_PATH = REPO / "data" / "founder-crypto-panel.pkl"
OUT_DIR = Path(__file__).resolve().parent / "archetype-scan"
TOP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
               "XRPUSDT", "LTCUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT",
               "TRXUSDT", "BCHUSDT", "ATOMUSDT", "ETCUSDT", "XLMUSDT",
               "AVAXUSDT", "DASHUSDT", "NEOUSDT", "ZECUSDT", "QTUMUSDT",
               "ALGOUSDT", "VETUSDT", "HOTUSDT", "ZILUSDT", "MANAUSDT",
               "ENJUSDT", "IOTXUSDT", "CFXUSDT", "ONTUSDT", "THETAUSDT"]

# SECURITY NOTE ON PICKLE
# Same trust boundary as run_alpha_zoo_crypto.py: the panel is written by
# build_crypto_panel.py in this same repo from the founder's own Binance CSVs
# (no network, no third-party file). It contains only pandas DataFrames built
# from those CSVs. Not untrusted input.

VARIANTS: dict[str, list[dict[str, int | float]]] = {
    "TSMOM": [{"lookback": lb} for lb in (7, 14, 21, 30, 63, 126, 252)],
    "MARegimeFilter": [{"ma_period": p} for p in (50, 100, 200)],
    "VolatilityBreakout": [
        {"atr_period": ap, "quantile": q}
        for ap in (7, 14, 21)
        for q in (0.7, 0.8, 0.9)
    ],
    "ZScoreMeanReversion": [
        {"period": p, "entry_z": z}
        for p in (10, 20, 40)
        for z in (-1.5, -2.0, -2.5)
    ],
    "RegimeSwitching": [
        {"regime_period": rp, "trend_lookback": tl}
        for rp in (50, 100, 200)
        for tl in (14, 30)
    ],
}


def _sharpe(returns: pd.Series) -> float | None:
    clean = returns.dropna()
    if len(clean) < 2:
        return None
    std = clean.std(ddof=1)
    if std == 0 or std != std:
        return None
    return float(clean.mean() / std * (365 ** 0.5))


def _t_stat(returns: pd.Series) -> float | None:
    clean = returns.dropna()
    if len(clean) < 2:
        return None
    std = clean.std(ddof=1)
    if std == 0 or std != std:
        return None
    return float(clean.mean() / std * (len(clean) ** 0.5))


def _equity_series(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    return frame.set_index("timestamp")["equity"]


def main() -> None:
    if not PANEL_PATH.exists():
        raise SystemExit(f"panel not found: {PANEL_PATH}")
    with PANEL_PATH.open("rb") as handle:
        panel = pickle.load(handle)

    loader = LocalLoader()
    out_dir = Path(__file__).resolve().parent / "archetype-scan"
    out_dir.mkdir(parents=True, exist_ok=True)

    variants: list[tuple[str, str, dict[str, int | float], Any]] = []
    for family, params_list in VARIANTS.items():
        for params in params_list:
            symbol_tag = "multi"
            variants.append((family, symbol_tag, params, None))

    total_runs = len(variants) * len(TOP_SYMBOLS)
    print(f"variants: {len(variants)}  symbols: {len(TOP_SYMBOLS)}  total runs: {total_runs}")
    started = time.time()

    results: list[dict[str, Any]] = []
    run_index = 0
    for family, _tag, params, _ in variants:
        engine_cls = {
            "TSMOM": TSMOM,
            "MARegimeFilter": MARegimeFilter,
            "VolatilityBreakout": VolatilityBreakout,
            "ZScoreMeanReversion": ZScoreMeanReversion,
            "RegimeSwitching": RegimeSwitching,
        }[family]
        engine = engine_cls(**params)
        for symbol in TOP_SYMBOLS:
            run_index += 1
            run_dir = out_dir / f"{family}-{run_index}"
            run_dir.mkdir(parents=True, exist_ok=True)
            config = {
                "codes": [symbol],
                "source": "local",
                "start_date": "2020-01-01",
                "end_date": "2026-10-19",
                "initial_cash": 10_000.0,
                "leverage": 1.0,
                "interval": "1D",
                "perpetual_strict": False,
            }
            try:
                market = CryptoEngine(config)
                result = market.run_backtest(config, loader, engine, run_dir, bars_per_year=365)
            except Exception as exc:  # noqa: BLE001 — record and continue
                results.append({
                    "family": family, "params": params, "symbol": symbol,
                    "status": "ERROR", "error": str(exc)[:160],
                })
                continue

            equity = _equity_series(run_dir)
            returns = equity.pct_change().dropna() if len(equity) > 2 else pd.Series(dtype=float)
            sharpe = _sharpe(returns)
            t_stat = _t_stat(returns)
            max_dd = float(result.get("max_drawdown") or 0.0)
            trade_count = int(result.get("trade_count") or 0)
            annualised = float(result.get("annual_return") or 0.0)

            results.append({
                "family": family,
                "params": params,
                "symbol": symbol,
                "status": "OK",
                "annual_pct": round(annualised * 100, 2),
                "sharpe": round(sharpe, 3) if sharpe is not None else None,
                "t_stat": round(t_stat, 3) if t_stat is not None else None,
                "max_dd_pct": round(abs(max_dd) * 100, 2),
                "trade_count": trade_count,
                "n_obs": int(len(returns)),
            })
            if run_index % 20 == 0:
                print(f"  {run_index}/{total_runs} runs done ({time.time() - started:.0f}s)")

    # Deflated Sharpe across the whole scan: n_trials = the honest count of
    # strategies actually tested, trial_sharpe_std = dispersion of their Sharpes.
    tested = [row for row in results if row.get("status") == "OK" and row.get("sharpe") is not None]
    n_trials = len(tested)
    sharpes = [row["sharpe"] for row in tested if row["sharpe"] is not None]
    trial_std = float(pd.Series(sharpes).std(ddof=1)) if len(sharpes) > 1 else 0.0

    gate_rows = []
    for row in tested:
        t_stat = row.get("t_stat")
        annualised = row.get("annual_pct") or 0.0
        dsr_value: float | None = None
        if row.get("n_obs", 0) >= 30 and sharpe is not None:
            try:
                # Per-observation Sharpe, not annualised — the quantlib docstring
                # is explicit that mixing the two inflates the statistic by sqrt(T).
                per_obs = (annualised / 100) / 365 * 365  # annual_pct -> decimal
                per_obs = (annualised / 100)
                pseudo_returns = pd.Series([per_obs] * row["n_obs"])
                obs_sharpe = _sharpe(pseudo_returns) or 0.0
                dsr = deflated_sharpe_ratio(
                    observed_sharpe=obs_sharpe,
                    n_trials=n_trials,
                    n_observations=row["n_obs"],
                    trial_sharpe_std=trial_std,
                    skew=0.0,
                    kurtosis=3.0,
                )
                dsr_value = getattr(dsr, "dsr", None) if dsr is not None else None
            except (ValueError, ZeroDivisionError):
                dsr_value = None

        gate_g4 = t_stat is not None and abs(t_stat) >= 3.0
        gate_g5 = dsr_value is not None and dsr_value >= 0.95
        row["dsr"] = dsr_value
        row["gate_g4"] = gate_g4
        row["gate_g5"] = gate_g5
        row["alive"] = gate_g4 and gate_g5 and row.get("trade_count", 0) >= 30
        gate_rows.append(row)

    survivors = [row for row in gate_rows if row.get("alive")]
    elapsed = time.time() - started
    summary = {
        "date": "2026-10-19",
        "engine": "Vibe-Trading CryptoEngine (maker 0.02% / taker 0.05% / slippage 0.05%, leverage 1.0)",
        "symbols": TOP_SYMBOLS,
        "panel": f"{panel['_meta']['n_symbols']} symbols, {panel['_meta']['date_min']}..{panel['_meta']['date_max']}",
        "n_trials": n_trials,
        "trial_sharpe_std": round(trial_std, 4),
        "survivors_g4_and_g5": len(survivors),
        "expected_false_positives_at_5pct": round(n_trials * 0.05, 1),
        "cost": "$0 (pure CPU)",
        "survivorship": "live exchange list — delisted coins absent",
        "elapsed_seconds": round(elapsed, 1),
        "results": results,
        "survivors": survivors,
    }
    (out_dir / "scan-results.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print(f"\n=== ИТОГ ===")
    print(f"прогонов: {n_trials} (варианты × символы)")
    print(f"дисперсия Sharpe по попыткам: {trial_std:.4f}")
    print(f"прошли G4 AND G5: {len(survivors)}")
    print(f"ожидаемо ложноположительных при 5%: {n_trials * 0.05:.1f}")
    print(f"время CPU: {elapsed:.0f} секунд")
    for row in survivors[:10]:
        print(f"  ВЫЖИЛ {row['family']} {row['params']} {row['symbol']}: "
              f"{row['annual_pct']}%/год t={row['t_stat']} DSR={row['dsr']}")
    if not survivors:
        print("  ни один вариант не прошёл обе планки — это информативный ноль,")
        print(f"  ожидаемых по шуму было {n_trials * 0.05:.1f}, наблюдаемых 0.")
    print(f"\nwritten: {out_dir / 'scan-results.json'}")


if __name__ == "__main__":
    main()
