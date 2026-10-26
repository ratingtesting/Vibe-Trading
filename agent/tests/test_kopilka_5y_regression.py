"""Регрессии на BTC-копилку за 5 лет (kopilka_5y.run_kopilka).

Закрывает баг, найденный 2026-10-25: при подтверждённом дне, когда BTC-резерва
НЕТ, код покупал актив на кэш и обнулял счёт — годовая доходность
становилась -100%. Возврат разрешён только если есть что возвращать
(btc_units > 0), как в эталонной btc_kopilka_13.run_overlay.

Также проверяется главное свойство наложения: оно не может СОЗДАТЬ деньги
из ничего — с итоговым копилкой итог не больше базы без копилки плюс
комиссии.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiki" / "founder"))

import kopilka_5y as kop  # noqa: E402


def _series(n: int, values: list[float], start: str = "2021-01-01") -> pd.Series:
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.Series(values, index=dates, dtype=float)


def test_return_rule_needs_btc_to_return() -> None:
    """Нет резерва -> нет возврата -> счёт не обнуляется.

    Стратегия падает так, что подтверждённое дно наступает, но BTC ещё нет.
    Старая логика покупала актив на пустой кэш и давала -100% годовых.
    """
    n = 200
    dates = pd.date_range("2021-01-01", periods=n, freq="D")
    # Сильное падение, затем восстановление выше 50-дневной средней.
    equity = pd.Series([100.0 * (1.0 - 0.5 * i / 60) if i < 60 else
                        100.0 * (0.5 + 0.5 * (i - 60) / 60) for i in range(n)],
                       index=dates, dtype=float)
    asset = _series(n, [100.0] * n)
    btc = _series(n, [50000.0] * n)

    result = kop.run_kopilka(equity, asset, btc)
    assert result["status"] == "OK"
    # Счёт не обнулён: итог строго больше нуля.
    assert result["final_value"] > 0.0
    assert result["annual_pct"] > -99.0
    # Возвратов не было: BTC нечего было возвращать.
    assert result["returns_to_asset"] == 0


def test_kopilka_never_creates_money() -> None:
    """Наложение не может сделать итог больше базы: переводы платят комиссию."""
    n = 300
    dates = pd.date_range("2021-01-01", periods=n, freq="D")
    equity = pd.Series([100.0 * (1.0 + 0.01 * i) for i in range(n)], index=dates, dtype=float)
    asset = _series(n, [100.0] * n)
    btc = _series(n, [50000.0] * n)

    result = kop.run_kopilka(equity, asset, btc, lock_threshold=0.10, lock_share=0.5)
    assert result["status"] == "OK"
    assert result["locks"] > 0, "при растущем счёте фиксация обязана произойти"
    # Итог с копилкой <= итог без копилки (комиссии и переводы только убавляют).
    assert result["final_value"] <= equity.iloc[-1] + 1e-9
    # Компоненты счёта сходятся с итогом.
    parts = (result["final_asset_value"] + result["final_btc_value"] + result["final_cash"])
    assert abs(parts - result["final_value"]) < 1e-6


def test_btc_units_are_never_negative() -> None:
    """Резерв не может уйти в минус при возвратах."""
    n = 400
    dates = pd.date_range("2021-01-01", periods=n, freq="D")
    # Волнообразный счёт: и фиксации, и подтверждённые дна.
    equity = pd.Series(
        [100.0 * (1.0 + 0.3 * ((i // 40) % 2) + 0.002 * i) for i in range(n)],
        index=dates, dtype=float)
    asset = _series(n, [100.0 + 0.5 * i for i in range(n)])
    btc = _series(n, [50000.0 + 20.0 * i for i in range(n)])

    result = kop.run_kopilka(equity, asset, btc)
    assert result["status"] == "OK"
    assert result["final_btc_units"] >= 0.0
    assert result["final_cash"] >= -1e-6
    assert result["final_value"] > 0.0


def test_components_sum_to_total() -> None:
    """Актив + BTC + кэш = итог (счёт не теряет и не создаёт)."""
    n = 250
    dates = pd.date_range("2021-01-01", periods=n, freq="D")
    equity = pd.Series([100.0 * (1.0 + 0.004 * i) for i in range(n)], index=dates, dtype=float)
    asset = _series(n, [100.0] * n)
    btc = _series(n, [40000.0] * n)

    result = kop.run_kopilka(equity, asset, btc)
    parts = result["final_asset_value"] + result["final_btc_value"] + result["final_cash"]
    assert abs(parts - result["final_value"]) < 1e-6
    assert result["btc_share_pct"] >= 0.0
    assert result["asset_share_pct"] >= 0.0
