"""Parent cross-checks: no real provider calls or strategy reruns.

Toy market inputs below are explicitly TEST FIXTURES, not financial results.
Existing historical observations are read, never changed.
"""
from __future__ import annotations

import asyncio
import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(r"C:\Projects\jev-vibe")
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "wiki" / "founder"))

import pandas as pd
from src.quantlib.multipletesting import deflated_sharpe_ratio
import risk_parity_portfolio as rp
from btc_overlay_test_v2 import run_overlay

out = {}
annual = 1.2318920281464467
trial_std_annual = 0.3424
common = dict(n_trials=1064, n_observations=2484, skew=0.0, kurtosis=3.0)
old = deflated_sharpe_ratio(observed_sharpe=annual, trial_sharpe_std=trial_std_annual, **common)
wrong_partial = deflated_sharpe_ratio(observed_sharpe=annual / math.sqrt(365), trial_sharpe_std=trial_std_annual, **common)
proper = deflated_sharpe_ratio(observed_sharpe=annual / math.sqrt(365), trial_sharpe_std=trial_std_annual / math.sqrt(365), **common)
out["dsr_scale_check"] = {
    "purpose": "Same legacy summary inputs; demonstrate scale bug, NOT final corrected universe verdict.",
    "old_annual_inputs": old.deflated_sharpe_ratio,
    "incorrect_partial_conversion_in_child_probe": wrong_partial.deflated_sharpe_ratio,
    "both_inputs_per_observation": proper.deflated_sharpe_ratio,
    "both_input_units_required": True,
}

# Two assets, two days in one month: a monthly buy-and-hold sleeve must drift.
idx = pd.date_range("2020-01-10", periods=2)
fixture = pd.DataFrame({"a": [0.10, 0.0], "b": [0.0, 0.10]}, index=idx)
w = pd.Series({"a": 0.5, "b": 0.5})
actual = rp._simulate(fixture, w, idx)
with patch.object(rp, "COST_BPS", 10000.0):
    high_cost = rp._simulate(fixture, w, idx)
monthly_hold_final = 0.5 * 1.10 + 0.5 * 1.10
actual_final = float((1.0 + actual).prod())
out["portfolio_accounting_fixture"] = {
    "fixture_only": True,
    "intended_monthly_hold_final": monthly_hold_final,
    "actual_function_final": actual_final,
    "implied_daily_fixed_weights_without_turnover_cost": True,
    "changing_cost_10bps_to_10000bps_changes_output": not actual.equals(high_cost),
}

# Constant BTC blocks recovery transfers. The gain-lock branch transfers net
# 'move' from the portfolio into BTC, but subtracts no fee from account NAV.
idx2 = pd.date_range("2020-01-01", periods=3)
p = pd.Series([0.0, 0.5, 0.0], index=idx2)
b = pd.Series([100.0, 100.0, 100.0], index=idx2)
actual_btc = run_overlay(p, b)
# Reproduce only the initial monthly reserve purchase before the gain event.
initial_port = 0.9
initial_cash = 0.1
reserve_sell = 0.15 * 1.001
portfolio_units = initial_port - reserve_sell
btc_units = (reserve_sell - reserve_sell * 0.001) / 100.0
nav_before_lock = portfolio_units * 1.5 + btc_units * 100.0 + initial_cash
out["btc_profit_transfer_fee_fixture"] = {
    "fixture_only": True,
    "nav_before_profit_lock": nav_before_lock,
    "nav_after_profit_lock_function": actual_btc["final_value"],
    "actual_fee_on_profit_transfer": nav_before_lock - actual_btc["final_value"],
    "expected_positive_fee": True,
    "note": "A separately fee-charged transfer should reduce NAV; here the difference is zero.",
}

# Correlations from the saved 13 return series; no verdict or optimisation.
series = rp._collect()
returns = pd.DataFrame(series).dropna()
corr = returns.corr()
vals = [float(corr.iloc[i, j]) for i in range(len(corr)) for j in range(i + 1, len(corr))]
out["legacy_13_correlation"] = {
    "count": len(series), "common_days": len(returns),
    "mean_pair_correlation": sum(vals) / len(vals) if vals else None,
    "max_pair_correlation": max(vals) if vals else None,
    "min_pair_correlation": min(vals) if vals else None,
    "label": "Legacy selected series, not an independent validation sample.",
}

path = Path(__file__).resolve().parent / "parent-math-checks.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
print("PARENT_MATH_EVIDENCE", path)
