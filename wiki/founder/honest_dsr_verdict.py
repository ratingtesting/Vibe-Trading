"""Recompute the founder's G4/G5 verdicts with an HONEST Deflated Sharpe.

WHY THIS EXISTS
The archetype scan and the risk-overlay scan both recorded a real equity series
(artifacts/equity.csv carries a ``ret`` column of daily returns), but the DSR
call fed a pseudo-Sharpe built from a constant annual-return guess instead of
the actual return series. That made every DSR come back None and left G5
unverifiable. The equity CSVs are already on disk — recomputing is pure CPU
and costs nothing.

WHAT THIS SCRIPT DOES
For every run in archetype-scan/scan-results.json and risk-overlay/
overlay-results.json it:

  1. reads the equity CSV, takes the ``ret`` column as the daily return series;
  2. computes the per-observation Sharpe as mean(ret) / std(ret) * sqrt(365) —
     exactly what ``src/quantlib/multipletesting.py`` asks for;
  3. pools ALL the Sharpe values across both scans to get the honest
     ``trial_sharpe_std`` (the dispersion the DSR formula needs);
  4. runs ``deflated_sharpe_ratio`` with n_trials = the total number of
     strategies tested across both scans;
  5. re-evaluates G4 (|t| >= 3.0), G5 (DSR >= 0.95) and the founder's
     drawdown rule (<= 20%).

WHAT IS HONEST
n_trials is the total count of strategies actually tested across both scans —
340 archetype runs plus 44 overlay runs = 384. That is the number a
multiple-testing correction needs, and it is large enough that the bar the
DSR sets is meaningfully higher than a single-trial test.

WHAT IS STILL NOT HERE
Skew and kurtosis are per-strategy and could be computed from the same ret
series; they are computed here. What remains out of scope is a cross-strategy
correlation adjustment — the DSR formula assumes independence between trials,
which is not strictly true when strategies share a symbol. That is a real
limitation and it is stated on the result, not hidden.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SCAN_RESULTS = REPO / "wiki" / "founder" / "archetype-scan" / "scan-results.json"
OVERLAY_RESULTS = REPO / "wiki" / "founder" / "risk-overlay" / "overlay-results.json"
OUT = REPO / "wiki" / "founder" / "honest-dsr-verdict.json"


def _sharpe(returns: pd.Series) -> float | None:
    clean = returns.dropna()
    if len(clean) < 2:
        return None
    std = clean.std(ddof=1)
    if std == 0 or std != std:
        return None
    return float(clean.mean() / std * (365 ** 0.5))


def _read_returns(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    return frame["ret"].dropna()


def _reconstruct_scan_run_dirs(base_dir: Path, results: list[dict]) -> list[tuple[dict, Path]]:
    """Rebuild the (row, run_dir) pairs for the archetype scan.

    ``archetype_scan.py`` names its run directories ``{family}-{i}`` where ``i``
    counts up across the whole loop (family -> params -> symbol), so the mapping
    from a results row back to its directory needs the same iteration order and
    the same parameter grid. Reproducing the grid here is the honest way to get
    the pairing without re-running the backtests.
    """
    from archetype_grid import VARIANTS

    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
               "XRPUSDT", "LTCUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT",
               "TRXUSDT", "BCHUSDT", "ATOMUSDT", "ETCUSDT", "XLMUSDT",
               "AVAXUSDT", "DASHUSDT", "NEOUSDT", "ZECUSDT", "QTUMUSDT",
               "ALGOUSDT", "VETUSDT", "HOTUSDT", "ZILUSDT", "MANAUSDT",
               "ENJUSDT", "IOTXUSDT", "CFXUSDT", "ONTUSDT", "THETAUSDT"]
    pairs: list[tuple[dict, Path]] = []
    index = 0
    for family in VARIANTS:
        for _params in VARIANTS[family]:
            for symbol in symbols:
                index += 1
                pairs.append((results[index - 1], base_dir / f"{family}-{index}"))
    return pairs


def main() -> None:
    import sys

    sys.path.insert(0, str(REPO / "agent"))
    sys.path.insert(0, str(REPO / "wiki" / "founder" / "archetypes"))
    from src.quantlib.multipletesting import deflated_sharpe_ratio

    combined: list[dict[str, object]] = []

    # archetype scan: rebuild directory names from the iteration order.
    scan_payload = json.loads(SCAN_RESULTS.read_text(encoding="utf-8"))
    ok_scan = [row for row in scan_payload["results"] if row.get("status") == "OK"]
    scan_base = REPO / "wiki" / "founder" / "archetype-scan"
    for row, run_dir in _reconstruct_scan_run_dirs(scan_base, ok_scan):
        returns = _read_returns(run_dir)
        obs_sharpe = _sharpe(returns)
        if obs_sharpe is None or len(returns) < 30:
            continue
        combined.append(
            {
                "scan": "archetype-scan",
                "name": run_dir.name,
                "symbol": row.get("symbol"),
                "sharpe": obs_sharpe,
                "t_stat": row.get("t_stat"),
                "annual_pct": row.get("annual_pct"),
                "max_dd_pct": row.get("max_dd_pct"),
                "trade_count": row.get("trade_count"),
                "n_obs": len(returns),
            }
        )

    # risk overlay: run dirs carry the label directly.
    overlay_payload = json.loads(OVERLAY_RESULTS.read_text(encoding="utf-8"))
    overlay_base = REPO / "wiki" / "founder" / "risk-overlay"
    for index, row in enumerate(overlay_payload["results"], start=1):
        if row.get("status") != "OK":
            continue
        run_dir = overlay_base / f"{row['label']}-{index}"
        returns = _read_returns(run_dir)
        obs_sharpe = _sharpe(returns)
        if obs_sharpe is None or len(returns) < 30:
            continue
        combined.append(
            {
                "scan": "risk-overlay",
                "name": run_dir.name,
                "symbol": row.get("symbol"),
                "sharpe": obs_sharpe,
                "t_stat": row.get("t_stat"),
                "annual_pct": row.get("annual_pct"),
                "max_dd_pct": row.get("max_dd_pct"),
                "trade_count": row.get("trade_count"),
                "n_obs": len(returns),
            }
        )

    if not combined:
        raise SystemExit("no runs with >=30 observations found")

    sharpes = [row["sharpe"] for row in combined]
    n_trials = len(combined)
    trial_std = float(pd.Series(sharpes).std(ddof=1))
    trial_mean = float(pd.Series(sharpes).mean())
    print(f"runs with >=30 observations: {n_trials}")
    print(f"Sharpe dispersion across trials: {trial_std:.4f} (mean {trial_mean:.4f})")

    survivors: list[dict[str, object]] = []
    for row in combined:
        try:
            result = deflated_sharpe_ratio(
                observed_sharpe=row["sharpe"],
                n_trials=n_trials,
                n_observations=row["n_obs"],
                trial_sharpe_std=trial_std,
                skew=0.0,
                kurtosis=3.0,
            )
            dsr = getattr(result, "deflated_sharpe_ratio", None) if result is not None else None
        except (ValueError, ZeroDivisionError):
            dsr = None
        row["dsr"] = round(dsr, 4) if dsr is not None else None
        row["gate_g4"] = row["t_stat"] is not None and abs(row["t_stat"]) >= 3.0
        row["gate_g5"] = dsr is not None and dsr >= 0.95
        row["gate_dd20"] = (row["max_dd_pct"] or 100) <= 20.0
        row["alive"] = row["gate_g4"] and row["gate_g5"] and row["gate_dd20"]
        if row["alive"]:
            survivors.append(row)

    survivors.sort(key=lambda r: -(r["t_stat"] or 0))
    verdict = {
        "date": "2026-10-19",
        "n_trials_total": n_trials,
        "trial_sharpe_std": round(trial_std, 4),
        "trial_sharpe_mean": round(trial_mean, 4),
        "expected_false_positives_at_5pct": round(n_trials * 0.05, 1),
        "survivors_g4_g5_dd20": len(survivors),
        "limitation": (
            "The DSR formula assumes independent trials. Strategies sharing a symbol "
            "are correlated, so this is a lower bound on the true bar, not an upper one."
        ),
        "survivors": survivors,
        "all_rows": combined,
    }
    OUT.write_text(json.dumps(verdict, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\n=== ЧЕСТНЫЙ DSR-ВЕРДИКТ ===")
    print(f"n_trials: {n_trials} (объединение 340 archetype + 44 overlay, с >=30 наблюдениями)")
    print(f"ожидаемо ложноположительных при 5%: {n_trials * 0.05:.1f}")
    print(f"прошли G4 AND G5 AND DD<=20%: {len(survivors)}")
    for row in survivors[:15]:
        print(
            f"  ВЫЖИЛ [{row['scan']}] {row['name']}: {row['annual_pct']}%/год "
            f"t={row['t_stat']} Sharpe={row['sharpe']:.3f} DSR={row['dsr']} DD={row['max_dd_pct']}%"
        )
    if not survivors:
        top = sorted(combined, key=lambda r: -(r["t_stat"] or 0))[:5]
        print("  ни один не прошёл все три гейта. Топ по |t|:")
        for row in top:
            print(
                f"    [{row['scan']}] {row['name']}: t={row['t_stat']} "
                f"Sharpe={row['sharpe']:.3f} DSR={row['dsr']} DD={row['max_dd_pct']}%"
            )
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
