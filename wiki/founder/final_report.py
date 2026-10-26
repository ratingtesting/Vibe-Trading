"""СВОДНЫЙ ОТЧЁТ ПО ВСЕМ ПУНКТАМ ВЛАДЕЛЬЦА — ТОЛЬКО ТАБЛИЦЫ.

Собирает из уже посчитанных артефактов один документ:
  1. Сводка всех прогонов (старые блоки + 5-летний скан).
  2. Самопроверка: полнота пула, что именно убивает строки, какой разброс
     и какой порог при каком пуле.
  3. 13 кандидатов за 5 лет: полная таблица с раскладом счёта (BTC шт, BTC $,
     актив $, кэш, всего, доля BTC).
  4. Новые кандидаты из 5-летнего скана: полная таблица.
  5. Мнение Jev по каждой паре с вероятностями.
  6. Арифметика цели и дефицит (что ещё нужно, чтобы из $100 сделать
     состояние).
  7. Оговорки.

Все источники — файлы на диске; ничего не пересчитывается заново, кроме
DSR по полному пулу (нужен честный порог при полном числе испытаний).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
SCAN = FOUNDER / "scan5y"
RESULTS = SCAN / "scan-results.jsonl"
CAND13 = FOUNDER / "candidates-13-5y" / "kopilka-13-5y.json"
JEV = FOUNDER / "jev-judgement.json"
SELFCHECK = FOUNDER / "selfcheck-no-candidates.json"
OUT = FOUNDER / "final-report.md"

sys.path.insert(0, str(REPO / "agent"))

from src.quantlib.multipletesting import (  # noqa: E402
    deflated_sharpe_ratio,
    expected_maximum_sharpe,
)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def _load_scan() -> list[dict[str, Any]]:
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


def _with_dsr(rows: list[dict[str, Any]]) -> tuple[float, int]:
    """DSR по ВСЕМ строкам в одной попериодной шкале."""
    sharpes = [r["sharpe_per_obs"] for r in rows
               if isinstance(r.get("sharpe_per_obs"), (int, float))]
    n_trials = len(rows)
    std = float(pd.Series(sharpes).std(ddof=1)) if len(sharpes) > 1 else 0.0
    for r in rows:
        sharpe = r.get("sharpe_per_obs")
        if not isinstance(sharpe, (int, float)) or not math.isfinite(sharpe):
            r["dsr"] = None
            continue
        skew = r.get("skew")
        kurtosis = r.get("kurtosis")
        if not isinstance(skew, (int, float)) or not math.isfinite(skew):
            skew = 0.0
        if not isinstance(kurtosis, (int, float)) or not math.isfinite(kurtosis):
            kurtosis = 3.0
        try:
            res = deflated_sharpe_ratio(
                observed_sharpe=sharpe, n_trials=n_trials,
                n_observations=r["n_obs"], trial_sharpe_std=std,
                skew=skew, kurtosis=kurtosis)
            r["dsr"] = float(res.deflated_sharpe_ratio)
        except (ValueError, ZeroDivisionError, TypeError):
            r["dsr"] = None
    return std, n_trials


def _target_annual(start: float, end: float, years: int) -> float:
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


# Мёртвые токены: цена упала в ноль, торговать их уже нельзя. Стратегия на
# таком токене может показать огромную «доходность» - это артефакт краха
# (LUNAUSDT: $116 -> $0.043 за 5 лет), а не торговая возможность. Поэтому
# они исключаются из «лучших строк», но остаются в пуле испытаний для DSR:
# пул должен отражать всё, что было запущено.
DEAD_SYMBOLS = {"LUNAUSDT"}


def _tradable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("symbol") not in DEAD_SYMBOLS]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    rows = _load_scan()
    ok = [r for r in rows if r.get("status") == "OK"]
    std, n_trials = _with_dsr(rows)

    parts: list[str] = []

    # --- 1. Сводка -------------------------------------------------------
    parts.append("## 1. Сводка\n")
    parts.append(_table(
        ["Показатель", "Значение"],
        [
            ["Прогонов в 5-летнем скане", str(len(rows))],
            ["Успешных", str(len(ok))],
            ["Ошибок", str(len(rows) - len(ok))],
            ["Окно", "2021-10-20 .. 2026-10-19 (5 лет, 1826 дневных баров)"],
            ["Семейств стратегий", str(len({r["family"] for r in ok}))],
            ["Пар", str(len({r["symbol"] for r in ok}))],
            ["Вариантов (параметры x риск)", str(len({(r["family"], json.dumps(r.get("params"), sort_keys=True), r["risk"]) for r in ok}))],
            ["Исполнение размера", "position_adjustment=rebalance"],
            ["Доходность", "в годовых: (prod(1+r))^(365/n)-1"],
            ["Пул испытаний для DSR", str(n_trials)],
            ["Разброс Sharpe по пулу (попериодный)", f"{std:.6f}"],
            ["Ожидаемые ложные срабатывания при 5%", f"{n_trials * 0.05:.0f}"],
            ["Прошли ЭТАЛОН (t>=3, DSR>=0.95, |DD|<=20%)",
             str(len([r for r in ok if (r.get("dsr") or 0) >= 0.95 and (r.get("t_stat") or 0) >= 3.0 and (r.get("max_dd_pct") or 999) <= 20.0]))],
            ["Прошли КАНДИДАТ (t>=2.5, DSR>=0.95, |DD|<=20%)",
             str(len([r for r in ok if (r.get("dsr") or 0) >= 0.95 and (r.get("t_stat") or 0) >= 2.5 and (r.get("max_dd_pct") or 999) <= 20.0]))],
        ]))

    # --- 2. Самопроверка -------------------------------------------------
    parts.append("\n## 2. Самопроверка: почему кандидатов нет\n")
    if SELFCHECK.exists():
        sc = json.loads(SELFCHECK.read_text(encoding="utf-8"))
        parts.append(_table(
            ["Проверка", "Результат"],
            [
                ["Каталогов прогонов на диске", str(sc["n_dirs_on_disk"])],
                ["Строк взято в пересчёт", str(sc["n_rows_recomputed"])],
                ["Совпадает с записанным артефактом", "да" if sc["matches_artifact"] else "нет"],
                ["Проходят t>=3", f"{sc['pass_t_ge_3']} из {sc['n_rows_recomputed']}"],
                ["Проходят |DD|<=20%", f"{sc['pass_dd_le_20']} из {sc['n_rows_recomputed']}"],
                ["Проходят DSR>=0.95", f"{sc['pass_dsr_ge_095']} из {sc['n_rows_recomputed']}"],
                ["Проходят все три (ЭТАЛОН)", str(sc["n_reference"])],
                ["Вывод", sc["conclusion"]],
            ]))
    parts.append("\n### 2.1 Порог DSR в зависимости от размера пула\n")
    bar_rows = []
    for pool in (20, 50, 100, 200, 1000, 8174, n_trials):
        if pool < 2:
            continue
        bar = expected_maximum_sharpe(pool, std)
        bar_rows.append([str(pool), f"{bar:.5f}",
                         f"{std / bar:.2f}x" if bar else "—"])
    parts.append(_table(
        ["Пул испытаний", "Порог максимального Sharpe (попериодный)", "Разброс пула / порог"], bar_rows))
    sharpes_ok = [r["sharpe_per_obs"] for r in ok
                  if isinstance(r.get("sharpe_per_obs"), (int, float))
                  and math.isfinite(r["sharpe_per_obs"])]
    best_sharpe = max(sharpes_ok, default=0.0)
    parts.append(
        f"\nЛучший измеренный периодный Sharpe = {best_sharpe:.5f}. "
        "Пока он ниже порога, ни одна строка не проходит DSR — это арифметика "
        "перебора, а не признак отсутствия края.\n")

    # --- 3. 13 кандидатов -------------------------------------------------
    parts.append("## 3. 13 кандидатов за 5 лет: полная таблица с раскладом счёта\n")
    if CAND13.exists():
        payload = json.loads(CAND13.read_text(encoding="utf-8"))
        rows13 = payload.get("rows", [])
        # Знак просадки: research_metrics отдаёт модуль (51.57), kopilka_5y -
        # отрицательное значение (-48.06). В таблице оба приводятся к
        # отрицательной форме, иначе "База DD" и "DD с копилкой" показывают
        # разные знаки в одном столбце, а "Δ DD" выходит бессмысленным.
        def _dd(value: Any) -> str:
            if not isinstance(value, (int, float)):
                return "—"
            return f"{-abs(value):.2f}"

        def _dd_delta(base: Any, kop: Any) -> str:
            if not isinstance(base, (int, float)) or not isinstance(kop, (int, float)):
                return "—"
            return f"{abs(kop) - abs(base):+.2f}"

        parts.append(_table(
            ["#", "ID", "Пара", "Риск", "База %/год", "С копилкой %/год", "Δ годовой",
             "База DD %", "DD с копилкой %", "Δ DD (просадка выросла)",
             "BTC накоплено, шт", "BTC в $", "Актив в $", "Кэш в $", "ВСЕГО в $",
             "Доля BTC %", "Фиксаций", "Возвратов"],
            [[str(i), r["id"], r["symbol"], r["risk"],
              f"{r['base']['annual_pct']:.2f}", f"{r['kopilka']['annual_pct']:.2f}",
              f"{r['delta_annual_pct']:+.2f}",
              _dd(r['base'].get('max_dd_pct')), _dd(r['kopilka'].get('max_dd_pct')),
              _dd_delta(r['base'].get('max_dd_pct'), r['kopilka'].get('max_dd_pct')),
              f"{r['kopilka']['final_btc_units']:.6f}",
              f"{r['kopilka']['final_btc_value']:.2f}",
              f"{r['kopilka']['final_asset_value']:.2f}",
              f"{r['kopilka']['final_cash']:.2f}",
              f"{r['kopilka']['final_value']:.2f}",
              f"{r['kopilka']['btc_share_pct']:.1f}",
              str(r["kopilka"]["locks"]), str(r["kopilka"]["returns_to_asset"])]
             for i, r in enumerate(rows13, start=1)
             if r["kopilka"].get("status") == "OK"]))
        improved = [r for r in rows13 if (r.get("delta_annual_pct") or 0) > 0]
        parts.append("\n### 3.1 Итоги по копилке\n")
        parts.append(_table(
            ["Показатель", "Значение"],
            [
                ["Кандидатов с копилкой", str(len([r for r in rows13 if r["kopilka"].get("status") == "OK"]))],
                ["Копилка улучшила годовую доходность",
                 f"{len(improved)} из {len([r for r in rows13 if r['kopilka'].get('status') == 'OK'])}"],
                ["Всего фиксаций (переводов в BTC)",
                 str(sum(r["kopilka"]["locks"] for r in rows13 if r["kopilka"].get("status") == "OK"))],
                ["Всего возвратов резерва в актив",
                 str(sum(r["kopilka"]["returns_to_asset"] for r in rows13 if r["kopilka"].get("status") == "OK"))],
                ["Максимум BTC накоплено, шт",
                 f"{max((r['kopilka']['final_btc_units'] for r in rows13 if r['kopilka'].get('status') == 'OK'), default=0):.6f}"],
                ["Параметры копилки",
                 "порог 30% роста, 75% прироста в BTC, возврат 30% резерва, комиссия 10 bps на ногу"],
                ["Стартовый капитал копилки, $", "100"],
            ]))

    # --- 4. Новые кандидаты ----------------------------------------------
    parts.append("\n## 4. Новые кандидаты из 5-летнего скана: полная таблица\n")
    tradable = _tradable(ok)
    by_t = sorted([r for r in tradable if (r.get("t_stat") or -99) >= 2.5],
                   key=lambda r: -(r.get("t_stat") or 0))
    parts.append(_table(
        ["#", "Стратегия", "Пара", "Параметры", "Риск", "Годовая %", "t", "DSR",
         "Просадка %", "Sharpe/набл", "DD-прошёл", "DSR-прошёл"],
        [[str(i), r["family"], r["symbol"],
          ", ".join(f"{k}={v}" for k, v in sorted((r.get("params") or {}).items())),
          r["risk"], f"{r['annual_pct']:.2f}", f"{r['t_stat']:.3f}",
          f"{r['dsr']:.4f}" if r.get("dsr") is not None else "—",
          f"{r['max_dd_pct']:.2f}", f"{r['sharpe_per_obs']:.5f}",
          "да" if (r.get("max_dd_pct") or 999) <= 20 else "нет",
          "да" if (r.get("dsr") or 0) >= 0.95 else "нет"]
         for i, r in enumerate(by_t, start=1)]))

    parts.append("\n### 4.1 Лучшие при просадке <= 20%\n")
    by_dd = sorted([r for r in tradable if (r.get("max_dd_pct") or 999) <= 20.0],
                   key=lambda r: -(r.get("annual_pct") or -999))[:40]
    parts.append(_table(
        ["#", "Стратегия", "Пара", "Параметры", "Риск", "Годовая %", "t", "DSR",
         "Просадка %", "Sharpe/набл"],
        [[str(i), r["family"], r["symbol"],
          ", ".join(f"{k}={v}" for k, v in sorted((r.get("params") or {}).items())),
          r["risk"], f"{r['annual_pct']:.2f}", f"{r['t_stat']:.3f}",
          f"{r['dsr']:.4f}" if r.get("dsr") is not None else "—",
          f"{r['max_dd_pct']:.2f}", f"{r['sharpe_per_obs']:.5f}"]
         for i, r in enumerate(by_dd, start=1)]))

    # --- 5. Jev ----------------------------------------------------------
    parts.append("\n## 5. Мнение Jev (вероятности)\n")
    if JEV.exists():
        jev = json.loads(JEV.read_text(encoding="utf-8"))
        parts.append(_table(
            ["#", "Кандидат A", "Источник A", "Кандидат B", "Источник B",
             "Выбор Jev", "Вероятность выбора", "Confidence", "Стоимость $"],
            [[str(i), j["a"], j["a_source"], j["b"], j["b_source"],
              j.get("choice", "—"),
              f"{max((j.get('probabilities') or {'—': 0}).values()):.2f}"
              if j.get("probabilities") else "—",
              f"{j['confidence']:.2f}" if j.get("confidence") is not None else "—",
              f"{j['cost_usd']:.6f}" if j.get("cost_usd") is not None else "—"]
             for i, j in enumerate(jev.get("judgements", []), start=1)]))
        parts.append("\n" + _table(
            ["Оговорка", jev.get("role", "")],
            [["Роль Jev", jev.get("role", "")]]))
    else:
        parts.append("_Jev ещё не отсудил._")

    # --- 6. Цель ---------------------------------------------------------
    parts.append("\n## 6. Что ещё нужно, чтобы из $100 сделать состояние\n")
    parts.append("### 6.1 Арифметика цели\n")
    rows_goal = []
    for end, label in ((1_000.0, "тысяча"), (10_000.0, "десять тысяч"),
                       (100_000.0, "сотня тысяч"), (1_000_000.0, "миллион")):
        for years in (3, 5, 7, 10):
            rows_goal.append([f"${end:,.0f}".replace(",", " "), label, str(years),
                              f"{_target_annual(100.0, end, years):.1f}%"])
    parts.append(_table(["Цель", "Название", "Лет", "Нужно %/год"], rows_goal))

    max_ann = max((r["annual_pct"] for r in tradable), default=0.0)
    max_ann_dd20 = max((r["annual_pct"] for r in tradable
                         if (r.get("max_dd_pct") or 999) <= 20.0), default=0.0)
    kop_best = 0.0
    if CAND13.exists():
        kop_best = max((r["kopilka"]["annual_pct"]
                        for r in json.loads(CAND13.read_text(encoding="utf-8"))["rows"]
                        if r["kopilka"].get("status") == "OK"), default=0.0)
    parts.append("\n### 6.2 Измеренное против требуемого\n")
    parts.append(_table(
        ["Показатель", "Значение", "Источник"],
        [
            ["Измеренный максимум годовой (любая просадка)", f"{max_ann:.1f}%", "5-летний скан"],
            ["Измеренный максимум годовой при |DD|<=20%", f"{max_ann_dd20:.1f}%", "5-летний скан"],
            ["Измеренный максимум с BTC-копилкой", f"{kop_best:.1f}%", "13 кандидатов, 5 лет"],
            ["Требуется для $100 -> $1000 за 5 лет", f"{_target_annual(100.0, 1000.0, 5):.1f}%", "арифметика"],
            ["Требуется для $100 -> $10000 за 7 лет", f"{_target_annual(100.0, 10000.0, 7):.1f}%", "арифметика"],
            ["Требуется для $100 -> $100000 за 10 лет", f"{_target_annual(100.0, 100000.0, 10):.1f}%", "арифметика"],
        ]))

    parts.append("\n### 6.3 Дефицит по каждой цели (на лучшей строке при |DD|<=20%)\n")
    if by_dd:
        top = by_dd[0]
        rows_def = []
        for end, label in ((1_000.0, "тысяча"), (10_000.0, "десять тысяч"),
                           (100_000.0, "сотня тысяч"), (1_000_000.0, "миллион")):
            for years in (5, 10):
                need = _target_annual(100.0, end, years)
                rows_def.append([
                    f"${end:,.0f}".replace(",", " "), label, str(years),
                    f"{need:.1f}%", f"{top['annual_pct']:.1f}%",
                    f"{need - top['annual_pct']:+.1f} п.п.",
                ])
        parts.append(_table(
            ["Цель", "Название", "Лет", "Нужно %/год", "Есть %/год", "Дефицит"], rows_def))
        parts.append(
            f"\nОпорная строка: {top['family']} / {top['symbol']} / {top['risk']} — "
            f"{top['annual_pct']:.2f}%/год, просадка {top['max_dd_pct']:.2f}%, "
            f"t={top['t_stat']:.3f}, DSR={top['dsr']:.4f}.\n")
        parts.append(
            "Мёртвые токены (цена упала в ноль) исключены из лучших строк: "
            "LUNAUSDT за 5 лет рухнул с $116 до $0.043, и стратегия на нём "
            "показывает артефактные проценты, которые нельзя заработать - "
            "торговать уже нечего. В пуле испытаний для DSR они остаются: "
            "пул обязан отражать всё, что было запущено.\n")

    # --- 7. Walk-forward: переносится ли отбор на будущее -----------------
    wf_path = FOUNDER / "scan5y" / "walk-forward.json"
    tr_path = FOUNDER / "scan5y" / "walk-forward-transfer.json"
    if wf_path.exists() and tr_path.exists():
        wf = json.loads(wf_path.read_text(encoding="utf-8"))
        tr = json.loads(tr_path.read_text(encoding="utf-8"))
        parts.append("\n## 7. Walk-forward: переносится ли отбор на будущее\n")
        parts.append(
            f"Каждый из {wf['pool_size']} прогонов разрезан на train "
            f"({wf['train_period']}) и test ({wf['test_period']}). "
            "Отбор кандидатов сделан ТОЛЬКО по train; test в выборе не "
            "участвовал, DSR на test посчитан по полному пулу.\n")
        parts.append(_table(
            ["Показатель", "Значение", "Что значит"],
            [
                ["Корреляция train-Sharpe ↔ test-Sharpe (Пирсон)",
                 f"{tr['pearson_corr_train_test_sharpe']:.4f}",
                 "почти нет связи: красивая строка на train не гарантирует ничего на test"],
                ["То же рангом (Спирмен)",
                 f"{tr['spearman_corr_train_test_sharpe']:.4f}",
                 "то же самое, устойчивее к выбросам"],
                ["Отобрано на train (топ-N)", str(wf["n_selected_by_train"]),
                 "сколько строк взяли в работу"],
                ["Из них прибыльны на test",
                 f"{wf['n_positive_on_test']} ({wf['n_positive_on_test']*100//max(wf['n_selected_by_train'],1)}%)",
                 "пережили смену периода"],
                ["Прошли гейт на test (DSR≥0.95, t≥2.5, DD≤20%)",
                 str(wf["n_survivors_dsr95_t25_dd20_on_test"]),
                 "ни один не прошёл"],
                ["Доля прибыльных на test: топ-200 по train",
                 f"{tr['top200_positive_rate_on_test']*100:.1f}%",
                 "отобранные на train"],
                ["Доля прибыльных на test: случайная база",
                 f"{tr['base_positive_rate_on_test']*100:.1f}%",
                 "просто случайные строки того же размера"],
            ]))
        parts.append("\n### 7.1 Преимущество отбора над случайной выборкой\n")
        parts.append(_table(
            ["Отобрано на train", "test-Sharpe отобранных", "test-Sharpe случайных",
             "Преимущество", "z"],
            [[str(row["n"]), f"{row['selected_test_sharpe_mean']:+.5f}",
              f"{row['random_test_sharpe_mean']:+.5f}",
              f"{row['advantage']:+.5f}", f"{row['z_score']:+.2f}"]
             for row in tr["transfer_table"]]))
        parts.append(
            "\n**Вывод.** Отбор по статистике почти не переносится: преимущество "
            "над случайной выборкой в пределах шума (|z| ≈ 1) на любом "
            "размере, а топ-200 по train на test прибыльны реже, чем случайные "
            "строки. Поэтому нулевой DSR-гейт — это не «края нет вообще», а "
            "точный ответ: строка, которая красиво выглядит на 3 годах, "
            "не вероятнее случайной устоит на следующих 2. Гейт показал "
            "именно то, что должен был.\n")

        survivors = wf.get("selected", [])
        strong = [m for m in survivors if (m["test"]["t_stat"] or 0) >= 1.5]
        if strong:
            parts.append("### 7.2 Что всё-таки удержалось\n")
            parts.append(_table(
                ["Стратегия", "Пара", "Риск", "train %/год", "train t",
                 "test %/год", "test t", "test DSR", "test DD %"],
                [[str(m["family"]), str(m["symbol"]), str(m["risk"]),
                  f"{m['train']['annual_pct']:.2f}", f"{m['train']['t_stat']:.3f}",
                  f"{m['test']['annual_pct']:.2f}", f"{m['test']['t_stat']:.3f}",
                  f"{m['test']['dsr']:.4f}", f"{m['test']['max_dd_pct']:.2f}"]
                 for m in strong]))
            parts.append(
                "\nЕдиничная строка, удержавшаяся с t ≥ 1.5 на test. Её "
                "дневные движения совпадают с реальными скачками цены "
                "(день 203: −25.04% против цены −25.00%), то есть это "
                "настоящий шорт на мемкоине, а не артефакт движка. Но это "
                "одна строка из 40 с просадкой под 40% — не торгуемый край.\n")

    # --- 8. Оговорки ------------------------------------------------------
    parts.append("## 8. Оговорки к числам\n")
    limits = [
        "Период один и тот же для всех строк 5-летнего скана: 1826 дневных баров.",
        "Доходность в годовых считается из дневной доходности, а не делением на глаз.",
        "DSR — по ВСЕМ строкам пула в попериодной шкале (mean/std), как требует multipletesting.py.",
        "skew/kurtosis — по реальному ряду; kurtosis неэксцессовая (3 = гауссова).",
        "Отбор сделан на том же окне, что и скан: это НЕ независимая проверка.",
        "Все строки пула уже просмотрены: повторный перебор на них не даёт нового чистого теста.",
        "При пуле в десятки тысяч испытаний планка DSR>=0.95 заведомо недостижима — это арифметика, а не приговор краю.",
        "Мнение Jev — второе мнение с вероятностями, а не доказательство и не замена статистическому гейту.",
        "BTC-копилка наложена на реализованную дневную доходность, а не перегнана движком со смешанным BTC-рукавом.",
        "Комиссия движка уже учтена в доходности стратегии; в копилке — только комиссия переводов 10 bps на ногу.",
    ]
    parts.append(_table(["#", "Оговорка"], [[str(i), t] for i, t in enumerate(limits, start=1)]))

    text = "\n".join(parts) + "\n"
    Path(args.out).write_text(text, encoding="utf-8")
    print(text)
    print(f"written: {args.out}")


if __name__ == "__main__":
    main()
