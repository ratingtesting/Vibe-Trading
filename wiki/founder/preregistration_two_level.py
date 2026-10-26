"""Two-level pre-registration for the founder transfer (declared 2026-10-19).

The founder's directive: keep t >= 3.0 as the REFERENCE bar, add a CANDIDATE
bar at t >= 2.5, and work the drawdown down with risk overlays. This file
fixes that as a pre-registration BEFORE the next round of runs, so the two
bars cannot be moved after seeing a result.

This is the founder's decision (Vibe-Trading transfer, 2026-10-19), not a
post-hoc relaxation: the parent project's bar was t >= 3.0 only, and the
second level is being added by the owner explicitly, with the caveat that a
CANDIDATE is not a confirmed edge — it needs forward-PAPER and a drawdown
check before it can trade.
"""

from __future__ import annotations

DATE_DECLARED = "2026-10-19"

REFERENCE_BAR = {
    "t_stat": 3.0,
    "dsr": 0.95,
    "max_drawdown_pct": 20.0,
    "trade_count_min": 30,
    "label": "REFERENCE — pre-registered edge (parent project's bar)",
}

CANDIDATE_BAR = {
    "t_stat": 2.5,
    "dsr": 0.95,
    "max_drawdown_pct": 20.0,
    "trade_count_min": 30,
    "label": "CANDIDATE — under observation, needs forward-PAPER before trade",
}

CANDIDATE_CAVEATS = (
    "A CANDIDATE is NOT a confirmed edge. The t-bar is relaxed, which raises the "
    "expected false-positive rate; at n trials the expected number of lucky 2.5-3.0 "
    "t-statistics grows with n. A CANDIDATE must clear forward-PAPER "
    "(>= 60 days, >= 30 trades, ECE <= 0.10, realised costs <= model x 1.5) before "
    "it trades, and its drawdown must stay under 20% with the risk overlay active."
)


def classify(t_stat: float | None, dsr: float | None, max_dd_pct: float | None,
             trade_count: int | None) -> str:
    """Classify a result as REFERENCE / CANDIDATE / REJECTED under the two bars."""
    if t_stat is None or dsr is None:
        return "NOT_COMPUTABLE"
    if max_dd_pct is None or trade_count is None:
        return "NOT_COMPUTABLE"
    if trade_count < REFERENCE_BAR["trade_count_min"]:
        return "REJECTED_INSUFFICIENT_TRADES"
    dd_ok = max_dd_pct <= REFERENCE_BAR["max_drawdown_pct"]
    if abs(t_stat) >= REFERENCE_BAR["t_stat"] and dsr >= REFERENCE_BAR["dsr"] and dd_ok:
        return "REFERENCE_EDGE"
    if abs(t_stat) >= CANDIDATE_BAR["t_stat"] and dsr >= CANDIDATE_BAR["dsr"] and dd_ok:
        return "CANDIDATE"
    return "REJECTED"
