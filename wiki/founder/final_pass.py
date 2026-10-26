"""Финальный проход: всё, что должно быть сделано ПОСЛЕ окончания скана.

Порядок владельца (26.10.26): «Остальное (прогнать копилку по новым
кандидатам, досчитать DSR по полному пулу, обновить панель и итоговые
таблицы) - делать после окончания прогона, иначе риск того, что мы
собъемся в подсчетах и допустим ошибки».

Этот скрипт - тот самый один проход. Он:
  1. Проверяет, что скан действительно завершён (все строки на месте).
  2. Считает DSR по ПОЛНОМУ пулу (старые упакованные + новый скан).
  3. Считает копилку по всем новым кандидатам (порог владельца + сетка).
  4. Пересобирает артефакт для панели.
  5. Строит итоговый отчёт (только таблицы).
  6. Отправляет кандидатов Jev-судье.

Порядок шагов фиксирован, потому что каждый следующий читает результат
предыдущего: отчёт не должен собираться по разным версиям чисел.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
PY = REPO / ".venv" / "Scripts" / "python.exe"

STEPS = [
    ("DSR по полному пулу (старые + новый 5-летний скан)",
     ["honest_dsr_final.py"]),
    ("Достижим ли гейт DSR >= 0.95 при этом пуле",
     ["dsr_reachability.py"]),
    ("Панель: артефакт 5-летнего скана",
     ["build_scan5y_panel.py"]),
    ("Копилка по новым кандидатам (порог владельца)",
     ["kopilka_5y.py", "--top", "40"]),
    ("Пороговая сетка копилки по новым кандидатам",
     ["kopilka_thresholds.py", "--top", "30"]),
    ("Итоговый отчёт (только таблицы)",
     ["final_report.py"]),
    ("Jev-судья: новые кандидаты против 13",
     ["jev_judge_candidates.py", "--pairs", "12"]),
    ("НЕЗАВИСИМАЯ перепроверка чисел (второй код, без импорта основного)",
     ["independent_check.py"]),
    ("Walk-forward: переносится ли отбор с train на test",
     ["walk_forward.py", "--workers", "7", "--top", "40"]),
    ("Walk-forward: перенос vs случайная выборка",
     ["walk_forward_transfer.py"]),
]


def scan_complete() -> tuple[bool, int, int]:
    """Скан завершён, если в манифесте строк больше нет незаписанных."""
    manifest = FOUNDER / "scan5y" / "jobs-manifest.json"
    results = FOUNDER / "scan5y" / "scan-results.jsonl"
    if not manifest.exists() or not results.exists():
        return False, 0, 0
    jobs = json.loads(manifest.read_text(encoding="utf-8"))
    done = set()
    with results.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    done.add(int(json.loads(line)["idx"]))
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
    return len(done) >= len(jobs), len(done), len(jobs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="запустить, даже если скан не завершён")
    args = parser.parse_args()

    complete, done, total = scan_complete()
    print(f"скан: {done} / {total} строк")
    if not complete and not args.force:
        print("\nскан НЕ завершён — финальный проход отложен (по указанию владельца).")
        print("Запустить принудительно: --force")
        return

    started = time.time()
    for title, script_args in STEPS:
        print(f"\n{'='*74}\n>> {title}\n{'='*74}", flush=True)
        result = subprocess.run(
            [str(PY), str(FOUNDER / script_args[0])] + list(script_args[1:]),
            cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        tail = "\n".join((result.stdout or "").strip().splitlines()[-14:])
        if tail:
            print(tail)
        if result.returncode != 0:
            print(f"\n!! шаг упал (exit {result.returncode}): {script_args[0]}")
            print((result.stderr or "")[-1500:])
        else:
            print(f"[ok] {script_args[0]}")

    print(f"\n{'='*74}")
    print(f"финальный проход завершён за {time.time()-started:.0f}s")
    print(f"отчёт: {FOUNDER / 'final-report.md'}")
    print("панель: http://localhost:5899/founder")


if __name__ == "__main__":
    main()
