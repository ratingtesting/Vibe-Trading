"""Apply the two-level pre-registration to the 384 honest runs, then judge
the survivors with Jev.

The two-level bar is the founder's directive (2026-10-19): keep t >= 3.0 as
the REFERENCE bar, add t >= 2.5 as a CANDIDATE bar with the caveat that a
CANDIDATE is not a confirmed edge. Both bars require DSR >= 0.95, drawdown
<= 20% after the risk overlay, and >= 30 trades.

STEPS
1. Recompute DSR from the equity CSVs (same wiring as honest_dsr_verdict.py).
2. Classify every run as REFERENCE_EDGE / CANDIDATE / REJECTED.
3. Take every CANDIDATE and REFERENCE_EDGE, compute the current regime inputs
   from the panel (last 30-day drift, realised vol, the strategy's own
   historical max drawdown), and ask Jev whether the assumed regime still
   holds.
4. Report: Jev's per-symbol verdict, and the combined list of what survives
   both the statistical bar AND Jev's regime check.

COST: Jev judging 16 candidates = 16 calls x \$0.0000144 = \$0.0002.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(REPO / "wiki" / "founder" / "archetypes"))
sys.path.insert(0, str(REPO / "wiki" / "founder"))

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402
from preregistration_two_level import CANDIDATE_CAVEATS, classify  # noqa: E402

SCAN_RESULTS = REPO / "wiki" / "founder" / "archetype-scan" / "scan-results.json"
OVERLAY_RESULTS = REPO / "wiki" / "founder" / "risk-overlay" / "overlay-results.json"
PANEL_PATH = REPO / "data" / "founder-crypto-panel.pkl"
OUT = REPO / "wiki" / "founder" / "two-level-verdict.json"

# SECURITY NOTE ON PICKLE
# Same trust boundary as build_crypto_panel.py / run_alpha_zoo_crypto.py: the
# panel is written by our own script from the founder's Binance CSVs. Not
# untrusted input.


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
    from archetype_grid import VARIANTS

    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
               "XRPUSDT", "LTCUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT"]
    pairs: list[tuple[dict, Path]] = []
    index = 0
    for family in VARIANTS:
        for _params in VARIANTS[family]:
            for symbol in symbols:
                index += 1
                pairs.append((results[index - 1], base_dir / f"{family}-{index}"))
    return pairs


def main() -> None:
    from jev_judge import JevJudgeError, judge_regime
    from src.quantlib.multipletesting import deflated_sharpe_ratio

    combined: list[dict[str, object]] = []

    scan_payload = json.loads(SCAN_RESULTS.read_text(encoding="utf-8"))
    ok_scan = [row for row in scan_payload["results"] if row.get("status") == "OK"]
    scan_base = REPO / "wiki" / "founder" / "archetype-scan"
    for row, run_dir in _reconstruct_scan_run_dirs(scan_base, ok_scan):
        returns = _read_returns(run_dir)
        obs_sharpe = _sharpe(returns)
        if obs_sharpe is None or len(returns) < 30:
            continue
        combined.append({
            "scan": "archetype-scan", "name": run_dir.name, "symbol": row.get("symbol"),
            "sharpe": obs_sharpe, "t_stat": row.get("t_stat"), "annual_pct": row.get("annual_pct"),
            "max_dd_pct": row.get("max_dd_pct"), "trade_count": row.get("trade_count"),
            "n_obs": len(returns), "run_dir": run_dir,
        })

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
        combined.append({
            "scan": "risk-overlay", "name": run_dir.name, "symbol": row.get("symbol"),
            "sharpe": obs_sharpe, "t_stat": row.get("t_stat"), "annual_pct": row.get("annual_pct"),
            "max_dd_pct": row.get("max_dd_pct"), "trade_count": row.get("trade_count"),
            "n_obs": len(returns), "run_dir": run_dir,
        })

    sharpes = [row["sharpe"] for row in combined]
    n_trials = len(combined)
    trial_std = float(pd.Series(sharpes).std(ddof=1))
    print(f"n_trials: {n_trials}  trial_sharpe_std: {trial_std:.4f}")

    for row in combined:
        try:
            result = deflated_sharpe_ratio(
                observed_sharpe=row["sharpe"], n_trials=n_trials, n_observations=row["n_obs"],
                trial_sharpe_std=trial_std, skew=0.0, kurtosis=3.0,
            )
            row["dsr"] = round(getattr(result, "deflated_sharpe_ratio", None), 4) if result else None
        except (ValueError, ZeroDivisionError):
            row["dsr"] = None
        row["verdict"] = classify(row["t_stat"], row["dsr"], row["max_dd_pct"], row["trade_count"])

    reference = [row for row in combined if row["verdict"] == "REFERENCE_EDGE"]
    candidates = [row for row in combined if row["verdict"] == "CANDIDATE"]
    print(f"REFERENCE_EDGE (t>=3, DSR>=0.95, DD<=20%): {len(reference)}")
    print(f"CANDIDATE      (t>=2.5, DSR>=0.95, DD<=20%): {len(candidates)}")
    print(f"caveat: {CANDIDATE_CAVEATS[:120]}...")

    # Regime inputs from the panel, per surviving symbol.
    panel = _pickle_load(PANEL_PATH)

    surviving = (reference + candidates)
    judgments: list[dict[str, object]] = []
    jev_cost = 0.0
    PER_CALL = 0.0000144
    for row in surviving:
        symbol = row["symbol"]
        close = panel["close"][symbol].dropna()
        if len(close) < 31:
            continue
        price = float(close.iloc[-1])
        drift = float((close.iloc[-1] / close.iloc[-31] - 1) * 100)
        vol = float(close.pct_change().tail(30).std(ddof=0) * (365 ** 0.5) * 100)
        try:
            judgment = judge_regime(symbol, price, drift, vol, float(row["max_dd_pct"]))
            jev_cost += PER_CALL
            judgments.append({"row": row["name"], "symbol": symbol, **judgment})
            print(f"  JEV {symbol}: choice={judgment['choice']} p={judgment['probabilities']} conf={judgment['confidence']}")
        except JevJudgeError as exc:
            judgments.append({"row": row["name"], "symbol": symbol, "error": str(exc)[:160]})
            print(f"  JEV {symbol}: ERROR {str(exc)[:120]}")

    summary = {
        "date": "2026-10-19",
        "n_trials": n_trials,
        "trial_sharpe_std": round(trial_std, 4),
        "reference_edges": len(reference),
        "candidates": len(candidates),
        "jev_calls": len(judgments),
        "jev_cost_usd": round(jev_cost, 6),
        "jev_judgments": judgments,
        "reference": [{k: v for k, v in row.items() if k != "run_dir"} for row in reference],
        "candidates": [{k: v for k, v in row.items() if k != "run_dir"} for row in candidates],
        "caveat": CANDIDATE_CAVEATS,
    }
    OUT.write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nwritten: {OUT}  (Jev cost: \${jev_cost:.6f})")


def _pickle_load(path):
    import pickle
    with path.open("rb") as handle:
        return pickle.load(handle)


if __name__ == "__main__":
    main()
