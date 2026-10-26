"""Дотянуть свежие дневные бары из архива Binance в локальные CSV.

Зачем: данные в data/binance-spot-1d/ кончаются 2026-10-19, а пре-
регистрация ждёт holdout с 2026-10-20. Binance API из этой локации
отдаёт 451 ("restricted location"), но АРХИВ data.binance.vision доступен
и содержит дневные файлы.

Скрипт:
  1. Для каждого локального CSV определяет последнюю дату.
  2. Скачивает недостающие дневные архивы (YYYY-MM-DD) с data.binance.vision.
  3. Дописывает строки в тот же CSV в том же формате.
  4. Пишет отчёт: что дотянуто, что недоступно, что не изменилось.

Безопасно: только дописывает, существующие строки не трогает (если дата
уже есть - пропускает), и записывает файл через временный, чтобы не
оставить обрезанный CSV при сбое.

Ограничения (признаю явно):
  - архив spot/daily публикуется с задержкой в сутки-двое, поэтому свежее
    вчерашнего дня может ещё не быть;
  - если архив вернул 404 (файла ещё нет), пара просто ждёт следующего
    запуска;
  - объём скачивания: 144 пары x ~7 дней = ~1000 маленьких zip.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "data" / "binance-spot-1d"
BASE = "https://data.binance.vision/data/spot/daily/klines"

USER_AGENT = "jev-research/1.0"


def last_date(path: Path) -> date | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2:
        return None
    try:
        return date.fromisoformat(rows[-1][0])
    except (ValueError, IndexError):
        return None


def fetch_day(symbol: str, day: date) -> list[list[str]] | None:
    """Скачивает дневной архив и возвращает строки klines как строки CSV."""
    url = f"{BASE}/{symbol}/1d/{symbol}-1d-{day.isoformat()}.zip"
    request = urllib.request.Request(url, headers={"user-agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = archive.namelist()[0]
        text = archive.read(name).decode("utf-8")
    out: list[list[str]] = []
    for line in text.strip().splitlines():
        parts = line.split(",")
        if len(parts) < 6:
            continue
        # В дневных архивах Binance метка времени в МИКРОСЕКУНДАХ
        # (1792454400000000), а не в миллисекундах, как в klines API.
        stamp = int(parts[0])
        if stamp > 10**15:
            stamp //= 1000
        day_str = date.fromtimestamp(stamp / 1000).isoformat()
        out.append([day_str, parts[1], parts[2], parts[3], parts[4], parts[5]])
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", default=date.today().isoformat(),
                        help="до какой даты тянуть (включительно)")
    parser.add_argument("--max-days", type=int, default=30,
                        help="максимум дней на пару за один запуск")
    parser.add_argument("--delay", type=float, default=0.12,
                        help="пауза между запросами, сек")
    parser.add_argument("--limit", type=int, default=0,
                        help="ограничить число пар (0 = все)")
    args = parser.parse_args()

    end = date.fromisoformat(args.end)
    files = sorted(DATA_DIR.glob("*.csv"))
    if args.limit:
        files = files[:args.limit]
    print(f"пар: {len(files)}, дотягиваем до {end}")

    # Проверка ДО перебора: если архива за end-дату ещё нет (Binance
    # публикует дневные файлы с задержкой в сутки-двое), то его не будет
    # и для остальных пар. Без этой проверки ежедневный запуск делал бы
    # 384 бесполезных запроса и ждал бы их.
    probe = fetch_day("BTCUSDT", end)
    if probe is None:
        print(f"архива за {end} ещё нет (Binance публикует с задержкой) - "
              f"нечего дотягивать")
        report = {
            "date": date.today().isoformat(), "end": end.isoformat(),
            "stats": {"pairs": len(files), "rows_added": 0, "days_added": 0,
                      "missing_archives": len(files), "errors": 0,
                      "already_current": 0},
            "per_pair": {},
            "note": f"архив за {end} ещё не опубликован - проверка не нужна",
        }
        out = REPO / "wiki" / "founder" / "data-update-report.json"
        out.write_text(json.dumps(report, indent=1, ensure_ascii=False),
                       encoding="utf-8")
        print(f"written: {out}")
        return

    stats = {"pairs": len(files), "rows_added": 0, "days_added": 0,
             "missing_archives": 0, "errors": 0, "already_current": 0}
    per_pair: dict[str, int] = {}

    for index, path in enumerate(files, start=1):
        symbol = path.stem
        # Символ с не-ASCII (например 币安人生USDT) нельзя положить в URL:
        # http.client кодирует адрес в ASCII и падает с UnicodeEncodeError.
        # Такие пары пропускаем - в data-bridge их тоже нет.
        if not symbol.isascii():
            stats["errors"] += 1
            continue
        current = last_date(path)
        if current is None:
            stats["errors"] += 1
            continue
        if current >= end:
            stats["already_current"] += 1
            continue

        start = current + timedelta(days=1)
        days = (end - start).days + 1
        if days > args.max_days:
            start = end - timedelta(days=args.max_days - 1)

        added_rows: list[list[str]] = []
        day = start
        while day <= end:
            try:
                rows = fetch_day(symbol, day)
            except (urllib.error.URLError, OSError, zipfile.BadZipFile) as exc:
                stats["errors"] += 1
                print(f"  {symbol} {day}: ошибка {type(exc).__name__}")
                break
            if rows is None:
                stats["missing_archives"] += 1
                day += timedelta(days=1)
                time.sleep(args.delay)
                continue
            added_rows.extend(rows)
            day += timedelta(days=1)
            time.sleep(args.delay)

        if not added_rows:
            continue

        existing: set[str] = set()
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.reader(fh):
                if row:
                    existing.add(row[0])

        fresh = [r for r in added_rows if r[0] not in existing]
        if not fresh:
            continue

        tmp = path.with_suffix(".csv.tmp")
        # Пишем текстом, а не csv.writer: writer пересобирает строку иначе
        # (добавляет кавычки вокруг каждой буквы), что ломает файл.
        with path.open(encoding="utf-8", newline="") as src:
            existing_lines = src.read().splitlines()
        header = existing_lines[0] if existing_lines else "date,open,high,low,close,volume"
        fresh_lines = [",".join(row) for row in fresh]
        tmp.write_text("\n".join([header] + existing_lines[1:] + fresh_lines) + "\n",
                       encoding="utf-8")
        tmp.replace(path)
        per_pair[symbol] = len(fresh)
        stats["rows_added"] += len(fresh)
        stats["days_added"] += len({r[0] for r in fresh})

        if index % 25 == 0:
            print(f"  {index}/{len(files)}: добавлено {stats['rows_added']} строк")

    report = {
        "date": date.today().isoformat(),
        "end": end.isoformat(),
        "stats": stats,
        "per_pair": per_pair,
        "note": ("Архив spot/daily публикуется с задержкой в сутки-двое; "
                 "404 означает, что файла ещё нет - пара ждёт следующего "
                 "запуска."),
    }
    out = REPO / "wiki" / "founder" / "data-update-report.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nдобавлено строк: {stats['rows_added']} в {len(per_pair)} пар")
    print(f"недоступных архивов: {stats['missing_archives']}, ошибок: {stats['errors']}, "
          f"уже актуальных: {stats['already_current']}")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
