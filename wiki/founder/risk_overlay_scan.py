"""Risk-overlay scan: run the 11 G4 survivors from archetype_scan.py with a
vol-targeting wrapper and see whether the drawdown drops below the canon's
20% while the return stays positive.

WHY: the 340-run scan found 11 strategies with |t| >= 3 and annual returns
+50% to +116%, but every one carried a 50-82% drawdown. The canon's rule —
a drawdown above 20% kills the account psychologically — means those verdicts
are not tradeable as-is. Vol targeting is the standard fix: scale the position
down when realised volatility is high, which trims return and drawdown
together and lets the Sharpe ratio decide.

WHAT THIS RUNS
The 11 G4 survivors from archetype-scan/scan-results.json, each wrapped in
VolTargeted at three target-vol levels (10%, 15%, 20% annualised), plus a
DrawdownThrottled variant at soft 15% / hard 35%. Same symbols, same engine
(CryptoEngine, leverage 1.0), same data (the founder panel).

WHAT IS REPORTED
Per-overlay rows: annual %, t, DSR (with n_trials = honest count of overlays
tested), max drawdown, and whether the result clears G4 + G5 + DD <= 20%.
A survivor needs all three.

NO LLM. Cost is CPU time only.
"""

from __future__ import annotations

import json
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
    DrawdownThrottled,
    MARegimeFilter,
    RegimeSwitching,
    TSMOM,
    VolTargeted,
    VolatilityBreakout,
    ZScoreMeanReversion,
)

PANEL_PATH = REPO / "data" / "founder-crypto-panel.pkl"
SCAN_RESULTS = Path(__file__).resolve().parent / "archetype-scan" / "scan-results.json"
OUT_DIR = Path(__file__).resolve().parent / "risk-overlay"


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
    if not SCAN_RESULTS.exists():
        raise SystemExit("run archetype_scan.py first")
    scan = json.loads(SCAN_RESULTS.read_text(encoding="utf-8"))
    survivors = [row for row in scan["results"]
                 if row.get("status") == "OK" and row.get("t_stat") is not None
                 and abs(row["t_stat"]) >= 3.0]
    print(f"G4 survivors from the scan: {len(survivors)}")

    base_classes = {
        "TSMOM": TSMOM,
        "MARegimeFilter": MARegimeFilter,
        "VolatilityBreakout": VolatilityBreakout,
        "ZScoreMeanReversion": ZScoreMeanReversion,
        "RegimeSwitching": RegimeSwitching,
    }

    overlays: list[tuple[str, Any]] = []
    for row in survivors:
        family = row["family"]
        params = row["params"]
        symbol = row["symbol"]
        base = base_classes[family](**params)
        for target_vol in (0.10, 0.15, 0.20):
            overlays.append((
                f"{family}-{symbol}-vol{int(target_vol*100)}",
                symbol,
                VolTargeted(base, target_vol=target_vol),
            ))
        overlays.append((
            f"{family}-{symbol}-ddthrottle",
            symbol,
            DrawdownThrottled(base, soft_dd=0.15, hard_dd=0.35),
        ))

    print(f"overlay runs: {len(overlays)}")

    loader = LocalLoader()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()

    results: list[dict[str, Any]] = []
    for index, (label, symbol, engine) in enumerate(overlays, start=1):
        run_dir = OUT_DIR / f"{label}-{index}"
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
        except Exception as exc:  # noqa: BLE001
            results.append({"label": label, "symbol": symbol, "status": "ERROR", "error": str(exc)[:160]})
            continue

        equity = _equity_series(run_dir)
        returns = equity.pct_change().dropna() if len(equity) > 2 else pd.Series(dtype=float)
        sharpe = _sharpe(returns)
        t_stat = _t_stat(returns)
        annualised = float(result.get("annual_return") or 0.0)
        max_dd = float(result.get("max_drawdown") or 0.0)
        trade_count = int(result.get("trade_count") or 0)

        results.append({
            "label": label,
            "symbol": symbol,
            "status": "OK",
            "annual_pct": round(annualised * 100, 2),
            "sharpe": round(sharpe, 3) if sharpe is not None else None,
            "t_stat": round(t_stat, 3) if t_stat is not None else None,
            "max_dd_pct": round(abs(max_dd) * 100, 2),
            "trade_count": trade_count,
            "n_obs": int(len(returns)),
        })
        if index % 10 == 0:
            print(f"  {index}/{len(overlays)} done ({time.time() - started:.0f}s)")

    # DSR across the overlays: n_trials = the honest count of overlay strategies tested.
    tested = [row for row in results if row.get("status") == "OK" and row.get("sharpe") is not None]
    n_trials = len(tested)
    sharpes = [row["sharpe"] for row in tested if row["sharpe"] is not None]
    trial_std = float(pd.Series(sharpes).std(ddof=1)) if len(sharpes) > 1 else 0.0

    survivors_out: list[dict[str, Any]] = []
    for row in tested:
        t_stat = row.get("t_stat")
        annualised = row.get("annual_pct") or 0.0
        max_dd = row.get("max_dd_pct") or 100.0
        dsr_value: float | None = None
        if row.get("n_obs", 0) >= 30 and abs(t_stat or 0) >= 1:
            per_obs = (annualised / 100) / 365
            pseudo = pd.Series([per_obs] * row["n_obs"])
            obs_sharpe = _sharpe(pseudo) or 0.0
            try:
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
        row["dsr"] = dsr_value
        row["gate_g4"] = t_stat is not None and abs(t_stat) >= 3.0
        row["gate_g5"] = dsr_value is not None and dsr_value >= 0.95
        row["gate_dd20"] = max_dd <= 20.0
        row["alive"] = row["gate_g4"] and row["gate_g5"] and row["gate_dd20"]
        if row["alive"]:
            survivors_out.append(row)

    elapsed = time.time() - started
    summary = {
        "date": "2026-10-19",
        "engine": "Vibe-Trading CryptoEngine, leverage 1.0, overlay=VolTargeted/DrawdownThrottled",
        "g4_source": "archetype-scan/scan-results.json (11 G4 survivors)",
        "n_trials": n_trials,
        "trial_sharpe_std": round(trial_std, 4),
        "survivors_g4_g5_dd20": len(survivors_out),
        "cost": "$0 (pure CPU)",
        "elapsed_seconds": round(elapsed, 1),
        "results": results,
        "survivors": survivors_out,
    }
    (OUT_DIR / "overlay-results.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding="utf-8"
    )

    print(f"\n=== РИСК-ОВЕРЛЕЙ: ИТОГ ===")
    print(f"прогонов: {n_trials}")
    print(f"прошли G4 + G5 + DD<=20%: {len(survivors_out)}")
    for row in survivors_out[:10]:
        print(f"  ВЫЖИЛ {row['label']}: {row['annual_pct']}%/год t={row['t_stat']} "
              f"DSR={row['dsr']} DD={row['max_dd_pct']}%")
    if not survivors_out:
        best = sorted(tested, key=lambda r: (r.get("max_dd_pct") or 100))[:5]
        print("  ни один не прошёл все три гейта. Лучшие по просадке:")
        for row in best:
            print(f"    {row['label']}: DD={row['max_dd_pct']}% год={row['annual_pct']}% "
                  f"t={row['t_stat']} DSR={row['dsr']}")
    print(f"\nwritten: {OUT_DIR / 'overlay-results.json'}  ({elapsed:.0f}s CPU)")


if __name__ == "__main__":
    main()
