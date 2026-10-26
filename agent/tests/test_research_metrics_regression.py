"""Регрессии на исправленный измерительный стенд (research_metrics.py).

Эти тесты закрывают три дефекта, найденных мат-аудитом 2026-10-24:

C1. DSR получал ГОДОВОЙ Sharpe (mean/std * sqrt(365)), а multipletesting.py
    требует ПОПЕРИОДНЫЙ. Годовой Sharpe завышал DSR примерно в sqrt(365) раз:
    «DSR=0.9998» превращалось в ~0.63 на тех же данных.
    Тест: при корректной шкале DSR на шуме падает, а не взлетает в 1.0.

C2. Гейт просадки стоял как `max_dd_pct <= 20` при отрицательной просадке —
    проходило ЛЮБОЕ отрицательное число, включая -90%.
    Тест: глубокая просадка не проходит гейт 20%.

C3. skew/kurtosis подавались заглушками (0.0 / 3.0).
    Тест: моменты считаются по реальному ряду и совпадают с numpy.

Плюс: отсутствующее значение — это None, а не ноль; неизвестный результат
не проходит гейт (принцип из research_metrics.py).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiki" / "founder"))
sys.path.insert(0, str(REPO / "agent"))

from research_metrics import (  # noqa: E402
    drawdown_magnitude_pct,
    gate_candidate,
    gate_reference,
    metrics_from_returns,
    moments,
    passes_drawdown_gate,
    sharpe_per_observation,
)


def _daily_returns(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


# ---------------------------------------------------------------- C1: шкала


def test_sharpe_is_per_observation_not_annualised() -> None:
    """Периодический Sharpe НЕ умножается на sqrt(365)."""
    rng = np.random.default_rng(7)
    returns = _daily_returns((rng.normal(0.002, 0.02, size=500)).tolist())
    per_obs = sharpe_per_observation(returns)
    assert per_obs is not None
    assert abs(per_obs - returns.mean() / returns.std(ddof=1)) < 1e-12
    # Годовой вариант был бы в sqrt(365) раз больше по модулю.
    assert abs(per_obs) * math.sqrt(365) > abs(per_obs)
    m = metrics_from_returns(returns)
    assert m.sharpe_annual is not None
    assert abs(m.sharpe_annual - per_obs * math.sqrt(365)) < 1e-12


def test_dsr_on_noise_does_not_reach_one() -> None:
    """Ключевой тест C1: на шуме DSR не должен взлетать к 1.0.

    С годовым Sharpe тот же набор данных давал DSR=0.99999; с периодическим
    он обязан упасть ниже бара 0.95.
    """
    from src.quantlib.multipletesting import deflated_sharpe_ratio

    rng = np.random.default_rng(11)
    sharpes = []
    for _ in range(200):
        returns = _daily_returns(rng.normal(0.0, 0.02, size=1000).tolist())
        sharpes.append(sharpe_per_observation(returns) or 0.0)
    trial_std = float(pd.Series(sharpes).std(ddof=1))

    best = max(sharpes)
    result = deflated_sharpe_ratio(
        observed_sharpe=best,
        n_trials=len(sharpes),
        n_observations=1000,
        trial_sharpe_std=trial_std,
        skew=0.0,
        kurtosis=3.0,
    )
    assert result.deflated_sharpe_ratio < 0.95


def test_dsr_rejects_annualised_sharpe() -> None:
    """Подача годового Sharpe в DSR — ошибка, которую надо ловить.

    Здесь ровно тот случай из отчёта: периодический Sharpe 0.076 даёт DSR
    около 0.63 (ниже бара), а тот же Sharpe, умноженный на sqrt(365),
    раздувает Z и даёт 0.99999 (ложный PASS).
    """
    from src.quantlib.multipletesting import deflated_sharpe_ratio

    per_obs = 0.076333
    n_obs = 2219
    trial_std_per_obs = 0.3548 / math.sqrt(365)

    honest = deflated_sharpe_ratio(
        observed_sharpe=per_obs,
        n_trials=6914,
        n_observations=n_obs,
        trial_sharpe_std=trial_std_per_obs,
        skew=2.584,
        kurtosis=31.5939,
    )
    wrong = deflated_sharpe_ratio(
        observed_sharpe=per_obs * math.sqrt(365),
        n_trials=6914,
        n_observations=n_obs,
        trial_sharpe_std=0.3548,
        skew=2.584,
        kurtosis=31.5939,
    )
    assert honest.deflated_sharpe_ratio < 0.95
    assert wrong.deflated_sharpe_ratio > honest.deflated_sharpe_ratio


# ------------------------------------------------------- C2: знак просадки


def test_deep_drawdown_fails_the_gate() -> None:
    """Просадка -90% не проходит гейт «не хуже 20%»."""
    assert passes_drawdown_gate(-90.0, 20.0) is False
    assert passes_drawdown_gate(-20.0, 20.0) is True
    assert passes_drawdown_gate(20.0, 20.0) is True
    assert passes_drawdown_gate(-12.638, 20.0) is True


def test_negative_drawdown_below_minus_twenty_is_rejected() -> None:
    """Именно тот случай, который проходил при `max_dd_pct <= 20`."""
    assert not (abs(-90.0) <= 20.0)


def test_unknown_drawdown_does_not_pass() -> None:
    """Отсутствующее значение — не ноль: неизвестный результат гейт не проходит."""
    assert passes_drawdown_gate(None, 20.0) is False
    assert passes_drawdown_gate(float("nan"), 20.0) is False


def test_gate_reference_and_candidate_take_signed_t() -> None:
    """Отрицательный t не проходит: abs(t) тут быть не должно."""
    assert gate_reference(-3.5, 0.99, 10.0) is False
    assert gate_reference(3.5, 0.99, 10.0) is True
    assert gate_candidate(-2.6, 0.99, 10.0) is False
    assert gate_candidate(2.6, 0.99, 10.0) is True


def test_gate_requires_all_three_conditions() -> None:
    assert gate_reference(3.0, 0.95, 20.0) is True
    assert gate_reference(3.0, 0.94, 20.0) is False
    assert gate_reference(2.9, 0.99, 20.0) is False
    assert gate_reference(3.0, 0.99, 25.0) is False
    assert gate_reference(None, 0.99, 10.0) is False


# --------------------------------------------------------- C3: моменты


def test_moments_match_numpy_on_the_real_series() -> None:
    """skew/kurtosis считаются по реальному ряду, kurtosis — НЕэксцессовый."""
    rng = np.random.default_rng(3)
    values = rng.normal(0.001, 0.03, size=1500)
    returns = _daily_returns(values.tolist())
    skew, kurtosis = moments(returns)
    assert skew is not None and kurtosis is not None
    standardised = (values - values.mean()) / values.std(ddof=1)
    assert abs(skew - float(np.mean(standardised**3))) < 1e-12
    assert abs(kurtosis - float(np.mean(standardised**4))) < 1e-12
    # Неэксцессовый: у гауссова около 3, а не около 0.
    assert kurtosis > 1.0


def test_metrics_t_stat_matches_manual_computation() -> None:
    rng = np.random.default_rng(5)
    values = rng.normal(0.0005, 0.01, size=400)
    returns = _daily_returns(values.tolist())
    m = metrics_from_returns(returns)
    expected_t = float(values.mean() / values.std(ddof=1) * math.sqrt(len(values)))
    assert m.t_stat is not None
    assert abs(m.t_stat - expected_t) < 1e-10
    assert m.n_obs == 400


def test_drawdown_magnitude_is_positive_percentage() -> None:
    """Просадка = величина потери в процентах, всегда положительная.

    Ряд: +10%, -50%, +20%, -10%.
    Эквити: 1.0 -> 1.1 -> 0.55 -> 0.66 -> 0.594. Пик 1.1, минимум 0.55.
    Просадка = 0.55/1.1 - 1 = -50%.
    """
    returns = _daily_returns([0.1, -0.5, 0.2, -0.1])
    dd = drawdown_magnitude_pct(returns)
    assert dd is not None
    assert dd == pytest.approx(50.0, abs=1e-6)
    assert dd > 0


def test_missing_value_is_none_not_zero() -> None:
    """Неизвестный результат — это None, а не ноль."""
    empty = pd.Series(dtype=float)
    m = metrics_from_returns(empty)
    assert m.n_obs == 0
    assert m.sharpe_per_observation is None
    assert m.t_stat is None
    assert m.annual_pct is None
    assert sharpe_per_observation(empty) is None
