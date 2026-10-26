"""Удаляет тяжёлые артефакты старых прогонов (после успешной упаковки).

Порядок обязателен: сначала pack_old_runs.py (без --apply) проверяет, что
данные упакованы и сходятся с оригиналами; ПОТОМ этот скрипт удаляет
тяжёлые файлы. Если упаковки нет — скрипт откажется работать.

ЧТО УДАЛЯЕТСЯ (на прогон):
  artifacts/trades.csv, positions.csv, target_positions.csv, fills.jsonl,
  metrics.csv, rebalance_notes.*, risk_xray.*, run_card.json, run_card.md,
  artifacts/ohlcv_*.csv
  -> 98828 файлов, ~4.9 ГБ

ЧТО ОСТАЁТСЯ:
  artifacts/equity.csv   - читают все скрипты (DSR, самопроверка, копилка)
  old-returns/returns/*.npz - компактный след: ret + close
  old-returns/metrics.jsonl - метрики всех прогонов
  все .py - сканеры можно перепрогнать

ПРОВЕРКА ПЕРЕД УДАЛЕНИЕМ
Каждый прогон обязан иметь npz в упаковке. Если нет - удаление этого
прогона пропускается и пишется в отчёт.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
PACK = FOUNDER / "old-returns" / "returns"

BLOCKS = ("scan-10k", "freqtrade-scan", "archetype-scan", "risk-overlay")
DROP = (
    "artifacts/trades.csv", "artifacts/positions.csv",
    "artifacts/target_positions.csv", "artifacts/fills.jsonl",
    "artifacts/metrics.csv", "artifacts/rebalance_notes.json",
    "artifacts/rebalance_notes.md", "artifacts/risk_xray.json",
    "artifacts/risk_xray.md", "run_card.json", "run_card.md",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not PACK.exists() or not any(PACK.glob("*.npz")):
        raise SystemExit("упаковки нет — сначала запусти pack_old_runs.py")

    freed = 0
    deleted = 0
    skipped = 0
    for block in BLOCKS:
        base = FOUNDER / block
        if not base.exists():
            continue
        for run in base.iterdir():
            if not run.is_dir():
                continue
            if not (PACK / f"{block}__{run.name}.npz").exists():
                skipped += 1
                continue
            targets = [run / name for name in DROP]
            targets += sorted(run.glob("artifacts/ohlcv_*.csv"))
            for path in targets:
                if not path.exists():
                    continue
                try:
                    freed += path.stat().st_size
                except OSError:
                    pass
                if args.dry_run:
                    deleted += 1
                    continue
                try:
                    path.unlink()
                    deleted += 1
                except OSError:
                    pass
        print(f"{block}: обработан", flush=True)

    # Пустые каталоги внутри прогонов убираем.
    if not args.dry_run:
        for block in BLOCKS:
            base = FOUNDER / block
            if not base.exists():
                continue
            for run in base.iterdir():
                if not run.is_dir():
                    continue
                try:
                    if not any(run.iterdir()):
                        shutil.rmtree(run, ignore_errors=True)
                except OSError:
                    pass

    mode = "можно удалить" if args.dry_run else "удалено"
    print(f"\n{mode} файлов: {deleted}")
    print(f"освобождено: {freed/1048576:.0f} МБ")
    if skipped:
        print(f"пропущено (нет упаковки): {skipped}")


if __name__ == "__main__":
    main()
