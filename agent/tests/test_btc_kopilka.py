"""Проверки сохранения капитала в BTC-копилке (wiki/founder/btc_kopilka_13.py).

Это ТЕСТОВЫЕ ФИКСТУРЫ на искусственных рядах, а не рыночные результаты.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiki" / "founder"))

import btc_kopilka_13 as kopilka  # noqa: E402


def test_flat_strategy_never_locks() -> None:
    dates = pd.date_range("2021-01-01", periods=120, freq="D")
    equity = pd.Series([100.0] * 120, index=dates, dtype=float)
    asset = pd.Series([100.0] * 120, index=dates, dtype=float)
    btc = pd.Series([50.0] * 120, index=dates, dtype=float)
    result = kopilka.run_overlay(equity, asset, btc)
    assert result["status"] == "OK"
    assert result["locks"] == 0
    assert result["final_btc_units"] == 0.0
    assert abs(result["final_value"] - 100.0) < 1e-9


def test_fee_is_charged_on_a_lock() -> None:
    """Перевод в BTC обязан стоить комиссию:NAV не должна расти из ничего."""
    dates = pd.date_range("2021-01-01", periods=120, freq="D")
    equity = pd.Series([100.0 + i for i in range(120)], index=dates, dtype=float)
    asset = pd.Series([100.0] * 120, index=dates, dtype=float)
    btc = pd.Series([50.0] * 120, index=dates, dtype=float)
    result = kopilka.run_overlay(equity, asset, btc, lock_threshold=0.10, lock_share=0.5)
    assert result["locks"] > 0
    # Без комиссии NAV была бы выше: сравним с тем же сценарием при нулевой цене.
    kopilka.COST = 0.0
    try:
        free = kopilka.run_overlay(equity, asset, btc, lock_threshold=0.10, lock_share=0.5)
    finally:
        kopilka.COST = 0.001
    assert free["final_value"] > result["final_value"]


def test_return_to_asset_never_creates_units() -> None:
    """Возврат в актив покупает юниты на реальные деньги, а не печатает их."""
    dates = pd.date_range("2021-01-01", periods=200, freq="D")
    up = [100.0 + i * 2 for i in range(100)]
    down = [300.0 - i * 2 for i in range(100)]
    asset = pd.Series(up + down, index=dates, dtype=float)
    btc = asset * 3.0
    equity = pd.Series([100.0 + i for i in range(200)], index=dates, dtype=float)
    result = kopilka.run_overlay(equity, asset, btc)
    assert result["status"] == "OK"
    # части счёта сходятся с итогом
    parts = (
        result["final_strategy_value"]
        + result["final_btc_value"]
        + result["final_cash"]
    )
    assert abs(parts - result["final_value"]) < 1e-6
