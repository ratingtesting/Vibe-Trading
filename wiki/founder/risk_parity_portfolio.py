"""Risk-parity portfolio over the 13 G4+G5 survivors.

GOAL (founder's plan step: DD<=20% with returns well above +7.5%/yr):
the 13 survivors have weakly-correlated returns (different symbols, different
archetypes). Equal-risk weighting across them should raise return-per-DD the
way single-symbol stacks cannot: diversification, not deeper de-levering.

METHOD, honest
- Weights = inverse realised vol of each survivor's daily returns (risk parity
  with 1 free parameter, no optimizer to overfit), renormalized to 1.
- Rebalanced monthly on the historical returns. Costs: 10 bps per unit turnover
  (same cost model the scans used).
- DEV/EVAL split: weights are FIT on 2020-01-01..2022-12-31 (DEV) and the
  portfolio is EVALUATED untouched on 2023-01-01..2026-10-19 (EVAL). The EVAL
  number is the honest one; the DEV number is shown for calibration only.
- Survivor selection is NOT re-done inside the portfolio: the 13 were chosen
  with knowledge of the full sample, so the EVAL window still carries a
  selection bias. Stated, not hidden.

Gate: EVAL t >= 2.5, EVAL max DD <= 20%, EVAL annual return reported.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SCAN = REPO / "wiki" / "founder" / "archetype-scan" / "scan-results.json"
OVERLAY = REPO / "wiki" / "founder" / "risk-overlay" / "overlay-results.json"
OUT = REPO / "wiki" / "founder" / "risk-parity-portfolio.json"

COST_BPS = 10.0  # per unit turnover, same model as the scans
DEV_END = pd.Timestamp("2022-12-31")


def _equity_returns(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    series = frame.set_index("timestamp")["equity"]
    return series.pct_change().dropna()


def _collect() -> dict[str, pd.Series]:
    """The G4+G5 survivor return series, keyed by a readable name."""
    verdict = json.loads((REPO / "wiki" / "founder" / "honest-dsr-verdict.json")
                         .read_text(encoding="utf-8"))
    g45 = [row for row in verdict["all_rows"]
           if row.get("gate_g4") and row.get("gate_g5")]
    series: dict[str, pd.Series] = {}
    for row in g45:
        run_dir = REPO / "wiki" / "founder" / row["scan"] / row["name"]
        ret = _equity_returns(run_dir)
        if len(ret) > 200:
            series[row["name"]] = ret
    return series


def _annual(ret: pd.Series) -> float:
    return float((1 + ret).prod() ** (365 / max(len(ret), 1)) - 1)


def _t_stat(ret: pd.Series) -> float:
    if len(ret) < 30 or ret.std(ddof=1) == 0:
        return float("nan")
    return float(ret.mean() / ret.std(ddof=1) * (len(ret) ** 0.5))


def _max_dd(ret: pd.Series) -> float:
    equity = (1 + ret).cumprod()
    return float((equity / equity.cummax() - 1).min())


def _simulate(returns: pd.DataFrame, weights: pd.Series, rets_index: pd.DatetimeIndex) -> pd.Series:
    """Monthly-rebalanced weighted portfolio with turnover costs."""
    port = pd.Series(0.0, index=rets_index)
    month = None
    w = weights.copy()
    for date in rets_index:
        if month != date.month:
            month = date.month
            turnover = float((w - weights).abs().sum())
            port.loc[date] -= turnover * COST_BPS / 10_000
            w = weights.copy()
        port.loc[date] = float((returns.loc[date] * w).sum())
    return port


def dev_weights_of(returns: "pd.DataFrame") -> dict[str, float]:
    """Inverse-vol weights fit on the DEV window (shared with the results page)."""
    dev = returns[returns.index <= DEV_END]
    raw: dict[str, float] = {}
    for name in dev.columns:
        vol = dev[name].std(ddof=1)
        raw[name] = 1.0 / vol if vol > 0 else 0.0
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def vol_targeted(port: "pd.Series", target_annual: float, window: int = 60) -> "pd.Series":
    """Scale position by clip(target_vol / trailing realised vol, 0, 1); no look-ahead."""
    daily_target = target_annual / (365 ** 0.5)
    scale = pd.Series(index=port.index, dtype=float)
    for i in range(len(port)):
        start = max(0, i - window)
        window_ret = port.iloc[start:i]
        vol = window_ret.std(ddof=1) if len(window_ret) > 20 else np.nan
        scale.iloc[i] = min(1.0, daily_target / vol) if vol and vol > 0 else 0.0
    return port * scale


def main() -> None:
    series = _collect()
    print(f"survivors with >200 return days: {len(series)}")
    returns = pd.DataFrame(series).dropna(how="all")
    common = returns.dropna()
    print(f"common days: {len(common)} ({common.index.min().date()} .. {common.index.max().date()})")

    weights = {}
    for name in common.columns:
        vol = common[name].std(ddof=1)
        weights[name] = 1.0 / vol if vol > 0 else 0.0
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}
    print("\nweights (inverse-vol, fit on DEV):")
    for name, w in sorted(weights.items(), key=lambda kv: -kv[1]):
        print(f"  {w:.3f}  {name}")

    dev = common[common.index <= DEV_END]
    evalr = common[common.index > DEV_END]
    dev_weights = {}
    for name in dev.columns:
        vol = dev[name].std(ddof=1)
        dev_weights[name] = 1.0 / vol if vol > 0 else 0.0
    total = sum(dev_weights.values())
    dev_weights = {k: v / total for k, v in dev_weights.items()}

    port_eval = _simulate(evalr, pd.Series(dev_weights), evalr.index)
    port_dev = _simulate(dev, pd.Series(dev_weights), dev.index)
    port_full = pd.concat([port_dev, port_eval])

    port_eval_vt = vol_targeted(port_eval, 0.15)
    port_full_vt = vol_targeted(port_full, 0.15)
    port_eval_vt12 = vol_targeted(port_eval, 0.12)
    port_full_vt12 = vol_targeted(port_full, 0.12)

    def entry(series: pd.Series, days: int | None) -> dict[str, Any]:
        return {"annual_pct": _annual(series) * 100, "t_stat": _t_stat(series),
                "max_dd_pct": _max_dd(series) * 100, "days": days or len(series)}

    result = {
        "date": "2026-10-23",
        "n_survivors": len(common.columns),
        "weights_dev": dev_weights,
        "dev": entry(port_dev, len(port_dev)),
        "eval": entry(port_eval, len(port_eval)),
        "full": entry(port_full, None),
        "eval_voltarget15": entry(port_eval_vt, len(port_eval_vt)),
        "full_voltarget15": entry(port_full_vt, None),
        "eval_voltarget12": entry(port_eval_vt12, len(port_eval_vt12)),
        "full_voltarget12": entry(port_full_vt12, None),
        "selection_bias_note": (
            "Survivor selection used the full sample, so the EVAL window still "
            "carries selection bias. The honest next step is forward-PAPER."
        ),
    }
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")

    print("\n=== РИСК-ПАРИТЕТ ПОРТФЕЛЬ (inverse-vol, monthly rebalance) ===")
    for window in ("dev", "eval", "full"):
        r = result[window]
        print(f"  {window.upper():5s}: {r['annual_pct']:+.2f}%/год  t={r['t_stat']:.3f}  DD={r['max_dd_pct']:.1f}%  ({r.get('days', '—')} дн.)")
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
