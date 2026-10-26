"""Honest DSR verdict over the scan-10k block 1 results.

Same wiring as honest_dsr_verdict.py: rebuild each run's daily returns from
artifacts/equity.csv, compute the per-run Sharpe, pool the Sharpe dispersion
across ALL trials (scan-10k 6030 + legacy 384), and run deflated_sharpe_ratio
with the pooled n_trials.

Run-dir reconstruction: scan_10k.py names dirs {family}-{risk}-{index} where
index counts up across the loop (family -> params -> symbol -> risk[raw, vol10,
vol12dd820]) — reproduced here against archetype_grid.VARIANTS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SCAN = REPO / "wiki" / "founder" / "scan-10k" / "scan-results.json"
OUT = REPO / "wiki" / "founder" / "scan-10k-dsr-verdict.json"

TOP_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
    "XRPUSDT", "LTCUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT",
    "TRXUSDT", "BCHUSDT", "ATOMUSDT", "ETCUSDT", "XLMUSDT",
    "AVAXUSDT", "DASHUSDT", "NEOUSDT", "ZECUSDT", "QTUMUSDT",
    "ALGOUSDT", "VETUSDT", "HOTUSDT", "ZILUSDT", "MANAUSDT",
    "ENJUSDT", "IOTXUSDT", "CFXUSDT", "ONTUSDT", "THETAUSDT",
]
RISK_ORDER = ["raw", "vol10", "vol12dd820"]


def _sharpe(returns: pd.Series) -> float | None:
    clean = returns.dropna()
    if len(clean) < 2:
        return None
    std = clean.std(ddof=1)
    if std == 0 or std != std:
        return None
    return float(clean.mean() / std * (365 ** 0.5))


def main() -> None:
    sys.path.insert(0, str(REPO / "agent"))
    sys.path.insert(0, str(REPO / "wiki" / "founder" / "archetypes"))
    from src.quantlib.multipletesting import deflated_sharpe_ratio
    from archetype_grid import VARIANTS

    scan = json.loads(SCAN.read_text(encoding="utf-8"))
    ok_rows = [r for r in scan["results"] if r.get("status") == "OK"]
    base = REPO / "wiki" / "founder" / "scan-10k"

    # rebuild index -> run_dir mapping in the same iteration order
    dirs: list[Path] = []
    index = 0
    for family, plist in VARIANTS.items():
        for _params in plist:
            for _symbol in TOP_SYMBOLS:
                for risk in RISK_ORDER:
                    index += 1
                    dirs.append(base / f"{family}-{risk}-{index}")
    assert len(dirs) == len(ok_rows), f"{len(dirs)} dirs vs {len(ok_rows)} rows"

    combined: list[dict[str, object]] = []
    for row, run_dir in zip(ok_rows, dirs):
        path = run_dir / "artifacts" / "equity.csv"
        if not path.exists():
            continue
        returns = pd.read_csv(path, parse_dates=["timestamp"])["ret"].dropna()
        if len(returns) < 30:
            continue
        sh = _sharpe(returns)
        if sh is None:
            continue
        combined.append({
            "name": run_dir.name, "family": row["family"], "risk": row["risk"],
            "symbol": row["symbol"], "sharpe": sh, "t_stat": row.get("t_stat"),
            "annual_pct": row.get("annual_pct"), "max_dd_pct": row.get("max_dd_pct"),
            "trade_count": row.get("trade_count"), "n_obs": len(returns),
        })

    if not combined:
        raise SystemExit("no runs with >=30 observations")

    # Pool across scan-10k (this) + legacy archetype-scan/overlay survivors.
    legacy = json.loads((REPO / "wiki" / "founder" / "honest-dsr-verdict.json")
                        .read_text(encoding="utf-8"))["all_rows"]
    all_sharpes = [row["sharpe"] for row in combined] + [row["sharpe"] for row in legacy]
    n_trials = len(all_sharpes)
    trial_std = float(pd.Series(all_sharpes).std(ddof=1))

    print(f"runs with >=30 obs: {len(combined)} | pooled n_trials: {n_trials} | trial std: {trial_std:.4f}")

    for row in combined:
        try:
            result = deflated_sharpe_ratio(
                observed_sharpe=row["sharpe"], n_trials=n_trials, n_observations=row["n_obs"],
                trial_sharpe_std=trial_std, skew=0.0, kurtosis=3.0,
            )
            row["dsr"] = round(getattr(result, "deflated_sharpe_ratio", None), 4) if result else None
        except (ValueError, ZeroDivisionError):
            row["dsr"] = None
        dd = row["max_dd_pct"] or -100
        row["gate_reference"] = (row["t_stat"] is not None and abs(row["t_stat"]) >= 3.0
                                 and row["dsr"] is not None and row["dsr"] >= 0.95 and dd >= -20)
        row["gate_candidate"] = (row["t_stat"] is not None and abs(row["t_stat"]) >= 2.5
                                 and row["dsr"] is not None and row["dsr"] >= 0.95 and dd >= -20)

    reference = sorted([r for r in combined if r["gate_reference"]], key=lambda r: -(r["annual_pct"] or 0))
    candidates = sorted([r for r in combined if r["gate_candidate"]], key=lambda r: -(r["annual_pct"] or 0))
    expected_fp = n_trials * 0.05

    verdict = {
        "date": "2026-10-23",
        "n_runs_block1": len(combined),
        "n_trials_pooled": n_trials,
        "trial_sharpe_std": round(trial_std, 4),
        "expected_false_positives_5pct": round(expected_fp, 1),
        "reference_edges": reference,
        "n_candidates": len(candidates),
        "candidates_top50": candidates[:50],
        "limitation": "DSR assumes independent trials; same-symbol strategies are correlated.",
    }
    OUT.write_text(json.dumps(verdict, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\n=== SCAN-10K ЧЕСТНЫЙ DSR ===")
    print(f"ожидаемо ложных при 5%: {expected_fp:.1f}")
    print(f"REFERENCE (t>=3 + DSR>=0.95 + DD<=20%): {len(reference)}")
    for row in reference[:15]:
        print(f"  {row['name']}: {row['annual_pct']:+.2f}%/год t={row['t_stat']:.3f} DSR={row['dsr']} DD={row['max_dd_pct']:.1f}%")
    print(f"CANDIDATE (t>=2.5 + DSR>=0.95 + DD<=20%): {len(candidates)}")
    for row in candidates[:10]:
        print(f"  {row['name']}: {row['annual_pct']:+.2f}%/год t={row['t_stat']:.3f} DSR={row['dsr']} DD={row['max_dd_pct']:.1f}%")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
