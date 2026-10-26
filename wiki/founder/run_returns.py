"""Единый доступ к сохранённой дневной доходности прогона.

ЗАЧЕМ
Старые прогоны ужаты: тяжёлые артефакты (trades, positions, fills, ohlcv,
run_card) удалены, а компактный след — .npz с дневной доходностью и ценой
актива — лежит в wiki/founder/old-returns/returns/. У нового 5-летнего
скана свой формат: wiki/founder/scan5y/returns/<idx>.npz.

Скрипты, которые пересчитывают DSR, проверяют копилку и делают
самопроверку, должны читать доходность ОТКУДА УГОДНО — из старых блоков
(equity.csv на месте) или из упакованного npz. Этот модуль даёт одну
функцию, которая разбирается с обоими источниками и НИКОГДА не
возвращает данные из разных источников для одного прогона.

ПРИОРИТЕТ ИСТОЧНИКОВ
1. npz упаковки (old-returns) — компактный, единый формат;
2. artifacts/equity.csv старых блоков — как есть, пока не удалён;
3. npz нового скана (scan5y/returns) — по индексу строки.

ДАТЫ
npz не хранит даты (это была бы основная часть размера). Даты восстанавливаются
по календарю: стратегия торговалась на дневных барах без пропусков, поэтому
для npz из упаковки дата = последние N баров символа из его CSV. Это
ровно то, что делает копилка, и проверено: хвост символа начинается ровно
с начала окна прогона.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OLD_PACK = FOUNDER / "old-returns" / "returns"
OLD_METRICS = FOUNDER / "old-returns" / "metrics.jsonl"
NEW_RETURNS = FOUNDER / "scan5y" / "returns"
NEW_RESULTS = FOUNDER / "scan5y" / "scan-results.jsonl"
CSV_DIR = REPO / "data" / "binance-spot-1d"


def _asset_close(symbol: str) -> pd.Series | None:
    """Закрытие актива из локального CSV (источник цен)."""
    path = CSV_DIR / f"{symbol}.csv"
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    dc = "date" if "date" in frame.columns else frame.columns[0]
    frame[dc] = pd.to_datetime(frame[dc])
    series = frame.set_index(dc)["close"].astype(float)
    return series[~series.index.duplicated(keep="last")].sort_index()


def load_old_metrics() -> dict[tuple[str, str], dict[str, Any]]:
    """Метрики упакованных старых прогонов: (block, name) -> метрики."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if not OLD_METRICS.exists():
        return out
    with OLD_METRICS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                out[(row["block"], row["name"])] = row
    return out


def load_old_return(block: str, name: str) -> tuple[np.ndarray, np.ndarray | None] | None:
    """Дневная доходность и (если есть) цена актива из упаковки."""
    path = OLD_PACK / f"{block}__{name}.npz"
    if not path.exists():
        return None
    data = np.load(path)
    ret = data["ret"].astype(float)
    close = data["close"].astype(float) if "close" in data else None
    return ret, close


def load_new_return(idx: int) -> np.ndarray | None:
    """Дневная доходность прогона нового 5-летнего скана."""
    path = NEW_RETURNS / f"{idx:06d}.npz"
    if not path.exists():
        return None
    return np.load(path)["ret"].astype(float)


def load_new_rows() -> list[dict[str, Any]]:
    """Строки результатов нового скана."""
    rows: list[dict[str, Any]] = []
    if not NEW_RESULTS.exists():
        return rows
    with NEW_RESULTS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def dates_for(symbol: str, n: int) -> pd.DatetimeIndex | None:
    """Последние n дневных дат символа — восстановление календаря прогона."""
    close = _asset_close(symbol)
    if close is None or len(close) < n:
        return None
    return close.index[-n:]
