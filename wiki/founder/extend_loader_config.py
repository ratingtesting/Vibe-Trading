"""Расширяет конфиг загрузчика на ВСЕ локальные пары с достаточной историей.

Зачем: конфиг ~/.vibe-trading/data-bridge/config.yaml перечислял 47 символов,
а в локальном хранилище их 384. Скан без полного списка молча пропускает
пары («no config entry for symbol») — это тихий обрыв охвата.

Что делает:
  1. Читает существующий config.yaml.
  2. Находит все CSV в data/binance-spot-1d с >= min_bars дневных баров.
  3. Дописывает недостающие записи, не трогая существующие (у них могут быть
     свои настройки колонок/форматов).
  4. Пишет бэкап перед изменением.

Безопасность: файл вне репозитория, в нём нет секретов (только пути к
локальным CSV). Бэкап создаётся рядом.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
CSV_DIR = REPO / "data" / "binance-spot-1d"
CONFIG = Path.home() / ".vibe-trading" / "data-bridge" / "config.yaml"

COLUMN_MAP = {
    "date": "date",
    "open": "open",
    "high": "high",
    "close": "close",
    "volume": "volume",
}


def count_bars(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as fh:
            return sum(1 for _ in fh) - 1
    except OSError:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-bars", type=int, default=1826)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    sources = list(config.get("sources") or [])
    have = {str(entry.get("symbol")) for entry in sources}

    eligible = sorted(
        path.stem for path in CSV_DIR.glob("*.csv")
        if count_bars(path) >= args.min_bars
    )
    missing = [symbol for symbol in eligible if symbol not in have]

    print(f"в конфиге сейчас: {len(have)} символов")
    print(f"локально с >={args.min_bars} баров: {len(eligible)}")
    print(f"не хватает записей: {len(missing)}")
    if missing[:10]:
        print(f"  пример: {missing[:10]}")

    if not missing:
        print("нечего добавлять")
        return
    if args.dry_run:
        print("dry-run: файл не изменён")
        return

    for symbol in missing:
        sources.append({
            "symbol": symbol,
            "type": "csv",
            "path": str((CSV_DIR / f"{symbol}.csv").resolve()).replace("\\", "/"),
            "columns": dict(COLUMN_MAP),
            "date_format": "%Y-%m-%d",
            "market": "crypto",
        })
    config["sources"] = sources

    backup = CONFIG.with_suffix(".yaml.bak")
    shutil.copy2(CONFIG, backup)
    CONFIG.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"записано: {CONFIG}  (бэкап: {backup})")
    print(f"символов теперь: {len(sources)}")


if __name__ == "__main__":
    main()
