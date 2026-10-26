"""Единый измерительный модуль для исследовательских вердиктов.

ЗАЧЕМ. Прежние обвязки мешали единицы: годовой Sharpe передавался в DSR,
который ждёт попериодный Sharpe, и дисперсия испытаний тоже была годовой.
Модуль фиксирует одну шкалу и даёт честные числа.

ПРАВИЛА, ЗАКРЕПЛЁННЫЕ ЗДЕСЬ
1. Sharpe для DSR — ПОПЕРИОДНЫЙ: mean(ret)/std(ret), без умножения на sqrt(365).
2. Дисперсия испытаний — в той же попериодной шкале.
3. Моменты (skew, kurtosis) считаются по реальному ряду доходностей:
   skew — стандартизованный третий момент, kurtosis — НЕэксцессовый
   четвёртый момент (3 для гауссова).
4. Просадка в артефактах отрицательная: гейт «просадка не хуже 20%»
   это |dd| <= 20, а НЕ dd <= 20. Знак проверяется явно.
5. Отсутствующее значение — это None, а не ноль: неизвестный результат
   не проходит гейт.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

GAUSSIAN_KURTOSIS = 3.0
ANNUALISATION = 365.0


@dataclass
class RunMetrics:
    """Метрики одного прогона в согласованной шкале."""
    n_obs: int
    sharpe_per_observation: float | None
    sharpe_annual: float | None
    t_stat: float | None
    skew: float | None
    kurtosis: float | None
    annual_pct: float | None
    max_dd_pct: float | None
    total_return_pct: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_obs": self.n_obs,
            "sharpe_per_observation": self.sharpe_per_observation,
            "sharpe_annual": self.sharpe_annual,
            "t_stat": self.t_stat,
            "skew": self.skew,
            "kurtosis": self.kurtosis,
            "annual_pct": self.annual_pct,
            "max_dd_pct": self.max_dd_pct,
            "total_return_pct": self.total_return_pct,
        }


def sharpe_per_observation(returns: Iterable[float]) -> float | None:
    """mean/std без аннуализации — та единица, которую ждёт DSR."""
    values = np.asarray(list(returns), dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return None
    spread = float(values.std(ddof=1))
    if not math.isfinite(spread) or spread <= 0:
        return None
    return float(values.mean() / spread)


def moments(returns: Iterable[float]) -> tuple[float | None, float | None]:
    """(skew, неэксцессовый kurtosis) по реальному ряду."""
    values = np.asarray(list(returns), dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 3:
        return None, None
    std = float(values.std(ddof=1))
    if std <= 0:
        return None, None
    centred = (values - values.mean()) / std
    skew = float(np.mean(centred**3))
    kurtosis = float(np.mean(centred**4))
    return skew, kurtosis


def drawdown_magnitude_pct(returns: pd.Series) -> float | None:
    """Просадка как величина потери (положительное число) в процентах."""
    clean = pd.Series(returns).dropna()
    if len(clean) < 2:
        return None
    equity = (1.0 + clean).cumprod()
    drawdown = float((equity / equity.cummax() - 1.0).min())
    return abs(drawdown) * 100.0


def metrics_from_returns(returns: pd.Series) -> RunMetrics:
    """Единый расчёт по ряду дневных доходностей."""
    clean = pd.Series(returns).dropna()
    n = len(clean)
    if n < 2:
        return RunMetrics(n, None, None, None, None, None, None, None, None)
    sharpe = sharpe_per_observation(clean.to_numpy())
    annual_sharpe = sharpe * math.sqrt(ANNUALISATION) if sharpe is not None else None
    std = float(clean.std(ddof=1))
    t_stat = float(clean.mean() / std * math.sqrt(n)) if std > 0 else None
    skew, kurtosis = moments(clean.to_numpy())
    equity = (1.0 + clean).cumprod()
    total_return = float(equity.iloc[-1] - 1.0) * 100.0
    annual_pct = (float((1.0 + clean).prod() ** (ANNUALISATION / n) - 1.0) * 100.0) if n else None
    return RunMetrics(
        n_obs=n,
        sharpe_per_observation=sharpe,
        sharpe_annual=annual_sharpe,
        t_stat=t_stat,
        skew=skew,
        kurtosis=kurtosis,
        annual_pct=annual_pct,
        max_dd_pct=drawdown_magnitude_pct(clean),
        total_return_pct=total_return,
    )


def passes_drawdown_gate(max_dd_pct: float | None, limit_pct: float = 20.0) -> bool:
    """Просадка не хуже лимита. Неизвестное значение гейт не проходит."""
    if max_dd_pct is None:
        return False
    if not math.isfinite(max_dd_pct):
        return False
    return abs(max_dd_pct) <= limit_pct


def deflated_sharpe(
    observed_sharpe_per_observation: float | None,
    n_trials: int,
    n_observations: int,
    trial_sharpe_std_per_observation: float,
    skew: float | None = None,
    kurtosis: float | None = None,
):
    """DSR с корректной шкалой. Возвращает None при нехватке данных."""
    if observed_sharpe_per_observation is None:
        return None
    if n_trials < 1 or n_observations < 2:
        return None
    from src.quantlib.multipletesting import deflated_sharpe_ratio

    try:
        return deflated_sharpe_ratio(
            observed_sharpe=observed_sharpe_per_observation,
            n_trials=n_trials,
            n_observations=n_observations,
            trial_sharpe_std=trial_sharpe_std_per_observation,
            skew=skew if skew is not None else 0.0,
            kurtosis=kurtosis if kurtosis is not None else GAUSSIAN_KURTOSIS,
        )
    except (ValueError, ZeroDivisionError):
        return None


def gate_reference(
    t_stat: float | None,
    dsr: float | None,
    max_dd_pct: float | None,
    t_bar: float = 3.0,
    dsr_bar: float = 0.95,
    dd_limit: float = 20.0,
) -> bool:
    """ЭТАЛОН: t >= 3, DSR >= 0.95, просадка <= 20%. t берётся со знаком."""
    if t_stat is None or dsr is None:
        return False
    return t_stat >= t_bar and dsr >= dsr_bar and passes_drawdown_gate(max_dd_pct, dd_limit)


def gate_candidate(
    t_stat: float | None,
    dsr: float | None,
    max_dd_pct: float | None,
    t_bar: float = 2.5,
    dsr_bar: float = 0.95,
    dd_limit: float = 20.0,
) -> bool:
    """КАНДИДАТ: t >= 2.5, DSR >= 0.95, просадка <= 20%."""
    if t_stat is None or dsr is None:
        return False
    return t_stat >= t_bar and dsr >= dsr_bar and passes_drawdown_gate(max_dd_pct, dd_limit)


def pooled_trial_std(sharpes: Sequence[float]) -> float | None:
    """Дисперсия Sharpe по всем испытаниям в ТОЙ ЖЕ шкале, что и наблюдаемый."""
    values = np.asarray([s for s in sharpes if s is not None and math.isfinite(s)], dtype=float)
    if values.size < 2:
        return None
    return float(values.std(ddof=1))
