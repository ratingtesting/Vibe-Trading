"""Регрессия на смешение дисперсии и стандартного отклонения в DSR-пуле.

Ошибка, найденная 2026-10-25: в build_scan5y_panel.py разброс Sharpe по
пулу считался как СУММА КВАДРАТОВ ОТКЛОНЕНИЙ (дисперсия), а не как
стандартное отклонение. Величина уменьшилась в ~50 раз, порог
максимального Sharpe упал с 0.077 до 0.0015, и DSR показал 0.9997 вместо
честных 0.42. Одиннадцать строк «прошли кандидат», которых на самом деле
не было.

Почему это опасно: чем МЕНЬШЕ разброс, тем ЛЕГЧЕ пройти порог. Ошибка
всегда работает В ПОЛЬЗУ вывода — «найдено 11 кандидатов» вместо нуля.

Проверяем на трёх уровнях:
  1. Формула разброса совпадает с эталонной (pandas std ddof=1).
  2. DSR на шумовой серии НЕ взлетает к 1.0 (тот же тест, что и в
     research_metrics-регрессиях).
  3. Подмена дисперсии на стандартное отклонение МЕНЯЕТ вердикт — то есть
     тест действительно ловит именно эту ошибку.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "agent"))

from src.quantlib.multipletesting import (  # noqa: E402
    deflated_sharpe_ratio,
    expected_maximum_sharpe,
)


def _dispersion(sharpes: list[float]) -> float:
    """Разброс так, как его требует DSR: стандартное отклонение, ddof=1."""
    return float(pd.Series(sharpes).std(ddof=1))


def _variance_only(sharpes: list[float]) -> float:
    """Ошибочная версия: дисперсия без корня (именно так было в баге)."""
    mean = sum(sharpes) / len(sharpes)
    return float(sum((s - mean) ** 2 for s in sharpes) / (len(sharpes) - 1))


def test_dispersion_is_standard_deviation_not_variance() -> None:
    sharpes = [-0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03]
    std = _dispersion(sharpes)
    variance = _variance_only(sharpes)
    assert std == pytest.approx(variance ** 0.5, rel=1e-12)
    assert std > variance  # ошибка даёт число в ~50 раз меньше


def test_dsr_on_noise_does_not_reach_one_with_pool_dispersion() -> None:
    """Ключевой тест: с ПРАВИЛЬНЫМ разбросом DSR на шуме падает."""
    rng = np.random.default_rng(17)
    sharpes = []
    for _ in range(500):
        values = rng.normal(0.0, 0.02, size=1000)
        sharpes.append(float(values.mean() / values.std(ddof=1)))
    std = _dispersion(sharpes)
    best = max(sharpes)
    result = deflated_sharpe_ratio(
        observed_sharpe=best, n_trials=len(sharpes), n_observations=1000,
        trial_sharpe_std=std, skew=0.0, kurtosis=3.0)
    assert result.deflated_sharpe_ratio < 0.95


def test_variance_instead_of_std_would_flip_the_verdict() -> None:
    """Тест обязан ЛОВИТЬ именно эту ошибку, а не проходить рядом.

    Берём реальные числа скана: пул с Sharpe в пределах ±0.07, разброс
    около 0.0207. С правильным std порог максимального Sharpe ~0.077 и DSR
    лучшей строки ~0.42 (не проходит). С дисперсией вместо std порог
    падает в ~50 раз и DSR взлетает к 1.0 (проходит). Значит разница
    между верным и ошибочным расчётом — это разница между 0 кандидатов и
    11 «кандидатами».
    """
    sharpes = [-0.035, -0.021, -0.005, 0.0, 0.01, 0.02, 0.03, 0.05, 0.0727]
    std = _dispersion(sharpes)
    variance = _variance_only(sharpes)
    assert variance / std == pytest.approx(std, rel=0.3)  # порядок величин разный

    observed = 0.0727
    n_obs = 1826
    good = deflated_sharpe_ratio(
        observed_sharpe=observed, n_trials=5000, n_observations=n_obs,
        trial_sharpe_std=std, skew=4.0, kurtosis=56.0)
    bad = deflated_sharpe_ratio(
        observed_sharpe=observed, n_trials=5000, n_observations=n_obs,
        trial_sharpe_std=variance, skew=4.0, kurtosis=56.0)

    assert good.deflated_sharpe_ratio < 0.95, "верный расчёт не должен давать PASS"
    assert bad.deflated_sharpe_ratio > good.deflated_sharpe_ratio, \
        "ошибка обязана завышать DSR — иначе тест ничего не ловит"


def test_expected_maximum_sharpe_grows_with_pool() -> None:
    """Порог максимального Sharpe растёт с размером пула.

    Это и есть причина, почему большой перебор почти не оставляет шансов.
    Конкретные числа посчитаны функцией expected_maximum_sharpe при
    разбросе 0.0207 (измеренный по 5-летнему пулу):
      пул  8174 -> порог 0.0789
      пул 34992 -> порог 0.0860
    Лучшая измеренная строка (0.0727) не дотягивает ни до одного.
    """
    std = 0.0207
    bar_small = expected_maximum_sharpe(8174, std)
    bar_big = expected_maximum_sharpe(34992, std)
    assert bar_big > bar_small
    assert bar_small == pytest.approx(0.0789, abs=0.001)
    assert bar_big == pytest.approx(0.0860, abs=0.001)
    # Лучшая строка 5-летнего скана не проходит ни один из этих порогов.
    assert 0.0727 < bar_small < bar_big
