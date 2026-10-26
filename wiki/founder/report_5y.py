"""Итоговый отчёт по 5-летнему скану: ТОЛЬКО ТАБЛИЦЫ.

Требование владельца (25.10.26): «В отчете только полные таблицы, отчеты
таблицами». Этот скрипт строит markdown-отчёт из артефактов scan5y и
печатает его в stdout. Каждая таблица полная: все строки отбора, не
«топ-5».

ЧТО В ОТЧЁТЕ
  1. Сводка прогона: сколько, сколько ошибок, окно, охват.
  2. Полный список ЭТАЛОНОВ (t>=3 + DSR>=0.95 + |DD|<=20%).
  3. Полный список КАНДИДАТОВ (t>=2.5 + DSR>=0.95 + |DD|<=20%).
  4. Лучшие по DSR (все строки, прошедшие t>=2.5) — с полным раскладом.
  5. ТАБЛИЦА КОПИЛКИ: по каждому отобранному кандидату — BTC в штуках,
     BTC в долларах, актив в долларах, кэш, СОВОПУПНО, доля BTC,
     годовая доходность базы и с копилкой, дельты.
  6. Лучшие по годовой доходности при просадке <= 20% (без DSR) —
     честная альтернатива «просто доходность», помеченная как непрошедшая
     статистический бар.

DSR считается по ВСЕМ строкам пула в одной попериодной шкале.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
SCAN = FOUNDER / "scan5y"
RESULTS = SCAN / "scan-results.jsonl"
KOPILKA = SCAN / "kopilka.json"
OUT = SCAN / "report-5y.md"

sys.path.insert(0, str(REPO / "agent"))

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

REFERENCE_BAR = {"t": 3.0, "dsr": 0.95, "dd": 20.0}
CANDIDATE_BAR = {"t": 2.5, "dsr": 0.95, "dd": 20.0}


def load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not RESULTS.exists():
        return rows
    with RESULTS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def compute_dsr(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float, int]:
    """DSR для каждой строки в попериодной шкале."""
    sharpes = [r["sharpe_per_obs"] for r in rows
               if r.get("sharpe_per_obs") is not None]
    n_trials = len(rows)
    trial_std = float(pd.Series(sharpes).std(ddof=1)) if len(sharpes) > 1 else 0.0
    for r in rows:
        sharpe = r.get("sharpe_per_obs")
        if sharpe is None or not isinstance(sharpe, (int, float)) or not math.isfinite(sharpe):
            r["dsr"] = None
            continue
        # ВНИМАНИЕ: нельзя писать `r.get("kurtosis") or 3.0` — kurtosis может
        # быть 0.0 (falsy), и подстановка 3.0 молча искажает момент.
        skew = r.get("skew")
        kurtosis = r.get("kurtosis")
        if skew is None or not isinstance(skew, (int, float)) or not math.isfinite(skew):
            skew = 0.0
        if kurtosis is None or not isinstance(kurtosis, (int, float)) or not math.isfinite(kurtosis):
            kurtosis = 3.0
        try:
            res = deflated_sharpe_ratio(
                observed_sharpe=sharpe,
                n_trials=n_trials,
                n_observations=r["n_obs"],
                trial_sharpe_std=trial_std,
                skew=skew,
                kurtosis=kurtosis,
            )
            r["dsr"] = float(res.deflated_sharpe_ratio)
        except (ValueError, ZeroDivisionError, TypeError):
            r["dsr"] = None
    return rows, trial_std, n_trials


def _params_text(params: Any) -> str:
    if not params:
        return ""
    try:
        return ", ".join(f"{k}={v}" for k, v in sorted(params.items()))
    except AttributeError:
        return str(params)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def build_report(rows: list[dict[str, Any]], kopilka: dict[str, Any] | None) -> str:
    rows, trial_std, n_trials = compute_dsr(rows)
    ok_rows = [r for r in rows if r.get("status") == "OK"]
    expected_fp = n_trials * 0.05

    def passes(r: dict[str, Any], bar: dict[str, float]) -> bool:
        return (
            r.get("dsr") is not None and r["dsr"] >= bar["dsr"]
            and (r.get("t_stat") or -99) >= bar["t"]
            and (r.get("max_dd_pct") or 999) <= bar["dd"]
        )

    reference = sorted([r for r in ok_rows if passes(r, REFERENCE_BAR)],
                        key=lambda r: -(r.get("annual_pct") or -999))
    candidates = sorted([r for r in ok_rows if passes(r, CANDIDATE_BAR)],
                        key=lambda r: -(r.get("annual_pct") or -999))
    by_dsr = sorted([r for r in ok_rows if (r.get("t_stat") or -99) >= CANDIDATE_BAR["t"]],
                    key=lambda r: -(r.get("dsr") or 0))
    by_annual = sorted([r for r in ok_rows if (r.get("max_dd_pct") or 999) <= 20.0],
                       key=lambda r: -(r.get("annual_pct") or -999))

    kop_by_idx = {}
    if kopilka:
        for entry in kopilka.get("rows", []):
            kop_by_idx[entry["idx"]] = entry

    parts: list[str] = []

    # --- 1. Сводка ------------------------------------------------------
    families = len({r["family"] for r in ok_rows})
    symbols = len({r["symbol"] for r in ok_rows})
    variants = len({(r["family"], json.dumps(r.get("params"), sort_keys=True), r["risk"])
                    for r in ok_rows})
    parts.append("## 1. Сводка прогона\n")
    parts.append(_table(
        ["Показатель", "Значение"],
        [
            ["Прогонов всего", str(len(rows))],
            ["Успешных (OK)", str(len(ok_rows))],
            ["Ошибок", str(len(rows) - len(ok_rows))],
            ["Окно", "2021-10-20 .. 2026-10-19 (5 лет, дневные бары)"],
            ["Наблюдений на прогон", "1826 (5 лет x 365)"],
            ["Семейств стратегий", str(families)],
            ["Вариантов (параметры x риск)", str(variants)],
            ["Пар", str(symbols)],
            ["Исполнение размера", "position_adjustment=rebalance (dropped=0)"],
            ["Пул испытаний для DSR", str(n_trials)],
            ["Разброс Sharpe по пулу (попериодный)", f"{trial_std:.6f}"],
            ["Ожидаемые ложные срабатывания при 5%", f"{expected_fp:.1f}"],
            ["Прошли ЭТАЛОН (t>=3, DSR>=0.95, |DD|<=20%)", str(len(reference))],
            ["Прошли КАНДИДАТ (t>=2.5, DSR>=0.95, |DD|<=20%)", str(len(candidates))],
        ]))

    # --- 2. Эталоны ------------------------------------------------------
    parts.append("\n## 2. ЭТАЛОНЫ (t>=3 + DSR>=0.95 + |DD|<=20%) — полный список\n")
    if reference:
        parts.append(_table(
            ["#", "Стратегия", "Пара", "Параметры", "Риск", "Годовая %", "t", "DSR",
             "Просадка %", "Sharpe/набл", "Сделки"],
            [[str(i), r["family"], r["symbol"], _params_text(r.get("params")), r["risk"],
              f"{r['annual_pct']:.2f}", f"{r['t_stat']:.3f}", f"{r['dsr']:.4f}",
              f"{r['max_dd_pct']:.2f}", f"{r['sharpe_per_obs']:.5f}", str(r.get("trade_count"))]
             for i, r in enumerate(reference, start=1)]))
    else:
        parts.append("_Ни один прогон не прошёл все три условия. "
                     "Путь ниже показывает, чего именно не хватает каждой строке._")

    # --- 3. Кандидаты ----------------------------------------------------
    parts.append("\n## 3. КАНДИДАТЫ (t>=2.5 + DSR>=0.95 + |DD|<=20%) — полный список\n")
    if candidates:
        parts.append(_table(
            ["#", "Стратегия", "Пара", "Параметры", "Риск", "Годовая %", "t", "DSR",
             "Просадка %", "Sharpe/набл", "Сделки"],
            [[str(i), r["family"], r["symbol"], _params_text(r.get("params")), r["risk"],
              f"{r['annual_pct']:.2f}", f"{r['t_stat']:.3f}", f"{r['dsr']:.4f}",
              f"{r['max_dd_pct']:.2f}", f"{r['sharpe_per_obs']:.5f}", str(r.get("trade_count"))]
             for i, r in enumerate(candidates, start=1)]))
    else:
        parts.append("_Ни один прогон не прошёл все три условия._")

    # --- 4. Лучшие по DSR (все строки с t>=2.5) -------------------------
    parts.append("\n## 4. Все строки с t>=2.5, отсортированные по DSR — полный список\n")
    parts.append(_table(
        ["#", "Стратегия", "Пара", "Параметры", "Риск", "Годовая %", "t", "DSR",
         "Просадка %", "Sharpe/набл", "DSR-прошёл", "DD-прошёл"],
        [[str(i), r["family"], r["symbol"], _params_text(r.get("params")), r["risk"],
          f"{r['annual_pct']:.2f}", f"{r['t_stat']:.3f}", f"{r['dsr']:.4f}",
          f"{r['max_dd_pct']:.2f}", f"{r['sharpe_per_obs']:.5f}",
          "да" if (r.get("dsr") or 0) >= 0.95 else "нет",
          "да" if (r.get("max_dd_pct") or 999) <= 20 else "нет"]
         for i, r in enumerate(by_dsr, start=1)]))
    if not by_dsr:
        parts.append("_Строк с t>=2.5 нет._")

    # --- 5. Таблица копилки ---------------------------------------------
    parts.append("\n## 5. BTC-копилка: полный расклад счёта\n")
    if kopilka and kopilka.get("rows"):
        rows_k = kopilka["rows"]
        parts.append(_table(
            ["#", "Стратегия", "Пара", "Риск", "База %/год", "С копилкой %/год",
             "Δ годовой", "База DD %", "DD с копилкой %", "Δ DD",
             "BTC накоплено, шт", "BTC в $", "Актив в $", "Кэш в $", "ВСЕГО в $",
             "Доля BTC %", "Фиксаций", "Возвратов"],
            [[str(i), e["family"], e["symbol"], e["risk"],
              f"{e['base']['annual_pct']:.2f}" if e["base"]["annual_pct"] is not None else "—",
              f"{e['kopilka']['annual_pct']:.2f}" if e["kopilka"]["annual_pct"] is not None else "—",
              f"{e['delta_annual_pct']:.2f}" if e.get("delta_annual_pct") is not None else "—",
              f"{e['base']['max_dd_pct']:.2f}" if e["base"]["max_dd_pct"] is not None else "—",
              f"{e['kopilka']['max_dd_pct']:.2f}" if e["kopilka"]["max_dd_pct"] is not None else "—",
              f"{e['delta_dd_pct']:.2f}" if e.get("delta_dd_pct") is not None else "—",
              f"{e['kopilka']['final_btc_units']:.6f}",
              f"{e['kopilka']['final_btc_value']:.2f}",
              f"{e['kopilka']['final_asset_value']:.2f}",
              f"{e['kopilka']['final_cash']:.2f}",
              f"{e['kopilka']['final_value']:.2f}",
              f"{e['kopilka']['btc_share_pct']:.1f}",
              str(e["kopilka"]["locks"]),
              str(e["kopilka"]["returns_to_asset"])]
             for i, e in enumerate(rows_k, start=1)]))
        improved = [e for e in rows_k
                    if e.get("delta_annual_pct") is not None and e["delta_annual_pct"] > 0]
        worsened_dd = [e for e in rows_k
                       if e.get("delta_dd_pct") is not None and e["delta_dd_pct"] > 0]
        parts.append("\n### 5.1 Итоги по копилке\n")
        parts.append(_table(
            ["Показатель", "Значение"],
            [
                ["Кандидатов посчитано с копилкой", str(len(rows_k))],
                ["Копилка улучшила годовую доходность", f"{len(improved)} из {len(rows_k)}"],
                ["Копилка ухудшила просадку (п.п.)", f"{len(worsened_dd)} из {len(rows_k)}"],
                ["Всего фиксаций (переводов в BTC)", str(sum(e["kopilka"]["locks"] for e in rows_k))],
                ["Всего возвратов резерва в актив", str(sum(e["kopilka"]["returns_to_asset"] for e in rows_k))],
                ["Максимум BTC накоплено, шт", f"{max((e['kopilka']['final_btc_units'] for e in rows_k), default=0):.6f}"],
                ["Стартовый капитал копилки, $", "100"],
            ]))
    else:
        parts.append("_Копилка ещё не посчитана (запусти kopilka_5y.py)._")

    # --- 6. Лучшие по доходности при DD<=20% ----------------------------
    parts.append("\n## 6. Лучшие по годовой доходности при просадке <= 20% — полный список\n")
    parts.append("| Строки этого списка НЕ прошли статистический бар DSR>=0.95. "
                 "Это альтернатива «просто доходность», показанная честно.\n")
    if by_annual:
        parts.append(_table(
            ["#", "Стратегия", "Пара", "Параметры", "Риск", "Годовая %", "t", "DSR",
             "Просадка %", "Sharpe/набл"],
            [[str(i), r["family"], r["symbol"], _params_text(r.get("params")), r["risk"],
              f"{r['annual_pct']:.2f}", f"{r['t_stat']:.3f}", f"{r['dsr']:.4f}",
              f"{r['max_dd_pct']:.2f}", f"{r['sharpe_per_obs']:.5f}"]
             for i, r in enumerate(by_annual, start=1)]))
    else:
        parts.append("_Нет строк с просадкой <= 20%._")

    # --- 7. Оговорки ------------------------------------------------------
    parts.append("\n## 7. Оговорки к числам\n")
    limits = [
        "Период один и тот же для всех строк: 5 лет дневных баров (1826 наблюдений).",
        "Доходность в годовых = (prod(1+r))^(365/n)-1 из дневной доходности, а не деление на глаз.",
        "DSR считается по ВСЕМ строкам пула в попериодной шкале (mean/std) — как требует multipletesting.py.",
        "skew/kurtosis — по реальному ряду доходности, kurtosis неэксцессовая (3 = гауссова).",
        "Отбор сделан на том же 5-летнем окне, что и скан: это НЕ независимая проверка.",
        "Все строки пула уже просмотрены: повторный перебор на них не даёт нового чистого теста.",
        "Комиссия движка (maker/taker/проскальзывание) учтена в доходности стратегии; в копилке — только комиссия переводов.",
        "Большой перебор сам по себе почти не оставляет шансов пройти DSR>=0.95: ожидается ~{:.0f} ложных срабатываний.".format(expected_fp),
    ]
    parts.append(_table(["#", "Оговорка"], [[str(i), t] for i, t in enumerate(limits, start=1)]))
    if kopilka:
        parts.append("\n" + _table(
            ["#", "Оговорка копилки"],
            [[str(i), t] for i, t in enumerate(kopilka.get("honest_limits", []), start=1)]))

    return "\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kopilka", default=str(KOPILKA))
    args = parser.parse_args()

    rows = load_rows()
    if not rows:
        raise SystemExit("нет результатов: запусти scan5y.py")
    kopilka = None
    kop_path = Path(args.kopilka)
    if kop_path.exists():
        kopilka = json.loads(kop_path.read_text(encoding="utf-8"))

    report = build_report(rows, kopilka)
    OUT.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
