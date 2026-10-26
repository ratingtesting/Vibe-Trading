"""ЧТО НУЖНО, ЧТОБЫ ИЗ $100 СДЕЛАТЬ СОСТОЯНИЕ (п.6 владельца).

Вопрос владельца: «Ты лучший трейдер всех времен и народов, которой из 100
долларов сделал состояние. Ты действуешь из предпосылки, что еще надо
сделать, чтобы сделать состояние из 100 долларов.»

Этот модуль отвечает ЧИСЛАМИ, а не словами:

1. АРИФМЕТИКА ЦЕЛИ. Сколько %/год нужно при сложном проценте, чтобы
   $100 превратились в заданную сумму за заданный срок, и какой просадки
   такой путь требует (сложный процент с просадкой — произведение, а не
   вычитание).

2. ЧТО ИЗМЕРЕНО. Лучшие результаты, реально посчитанные на диске:
   скан 5 лет (34992 прогона) и 13 кандидатов с копилкой. Из них
   отбираются те, что проходят бары, и сравниваются с требованием.

3. ДЕФИЦИТ. Для лучших строк считается: сколько ещё нужно %/год и какая
   просадка сверх измеренной, чтобы цель была достигнута за 5 и 10 лет.
   Это конкретные числа, а не «нужно лучше».

4. ЧТО ЭТО ЗНАЧИТ ПО РИСКУ. Какой просадки стоит цена такого дохода: по
   правилу f = доходность/просадка (а не 1/просадка) — потому что
   восстановление после -50% требует +100%.

ВЫХОД: таблицы в stdout + wiki/founder/goal-100-to-state.md
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
SCAN = FOUNDER / "scan5y"
RESULTS = SCAN / "scan-results.jsonl"
CANDIDATES = FOUNDER / "candidates-13-5y" / "kopilka-13-5y.json"
OUT = FOUNDER / "goal-100-to-state.md"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def target_annual_pct(start: float, end: float, years: int) -> float:
    """Требуемая годовая доходность (сложный процент)."""
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


def growth_with_drawdown(annual_pct: float, dd_pct: float, years: int) -> float:
    """Итог при сложном проценте с ежегодной просадкой dd (в процентах).

    Каждый год: (1 + r) * (1 - dd). Это реалистичная модель: доходность
    начисляется НЕ на пик, а просадка вычитается из счёта.
    """
    factor = (1.0 + annual_pct / 100.0) * (1.0 - dd_pct / 100.0)
    return factor ** years


def required_dd_for_target(annual_pct: float, start: float, end: float, years: int) -> float:
    """Какая просадка допустима при данной доходности, чтобы дойти до цели."""
    need = (end / start) ** (1.0 / years)
    have = 1.0 + annual_pct / 100.0
    if have <= 0:
        return 100.0
    dd = 1.0 - need / have
    return max(0.0, min(100.0, dd * 100.0))


def main() -> None:
    parts: list[str] = []

    # --- 1. Арифметика цели ---------------------------------------------
    parts.append("## 1. Арифметика цели: $100 -> состояние\n")
    targets = [(1_000.0, "тысяча"), (10_000.0, "десять тысяч"),
               (100_000.0, "сотня тысяч"), (1_000_000.0, "миллион")]
    rows = []
    for end, label in targets:
        for years in (3, 5, 7, 10):
            rows.append([f"${end:,.0f}".replace(",", " "), label, str(years),
                         f"{target_annual_pct(100.0, end, years):.1f}%"])
    parts.append(_table(["Цель", "Название", "Лет", "Нужно %/год (сложный процент)"], rows))
    parts.append(
        "\nЭто ТРЕБОВАНИЕ к исследованию, а не прогноз. Реальный путь "
        "с просадкой — это произведение (1+доходность)·(1−просадка) в год, "
        "поэтому таблица ниже.\n")

    # --- 2. Что измерено -----------------------------------------------
    rows_scan: list[dict[str, Any]] = []
    if RESULTS.exists():
        with RESULTS.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows_scan.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    ok = [r for r in rows_scan if r.get("status") == "OK"]

    cand13: list[dict[str, Any]] = []
    if CANDIDATES.exists():
        payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        cand13 = payload.get("rows", [])

    best_by_t = sorted(ok, key=lambda r: -(r.get("t_stat") or -99))[:10]
    best_dd = sorted([r for r in ok if (r.get("max_dd_pct") or 999) <= 20.0],
                      key=lambda r: -(r.get("t_stat") or -99))[:10]

    parts.append("## 2. Что реально измерено (5-летний скан, дневные бары)\n")
    parts.append(
        f"Прогонов в пуле: {len(rows_scan)} (успешных {len(ok)}). "
        "Полный отчёт со всеми строками — wiki/founder/scan5y/report-5y.md.\n")
    parts.append("### 2.1 Лучшие по t-статистике\n")
    parts.append(_table(
        ["#", "Стратегия", "Пара", "Риск", "Годовая %", "t", "Просадка %", "Sharpe/набл"],
        [[str(i), r["family"], r["symbol"], r["risk"], f"{r['annual_pct']:.2f}",
          f"{r['t_stat']:.3f}", f"{r['max_dd_pct']:.2f}", f"{r['sharpe_per_obs']:.5f}"]
         for i, r in enumerate(best_by_t, start=1)]))
    parts.append("\n### 2.2 Лучшие при просадке <= 20%\n")
    parts.append(_table(
        ["#", "Стратегия", "Пара", "Риск", "Годовая %", "t", "Просадка %", "Sharpe/набл"],
        [[str(i), r["family"], r["symbol"], r["risk"], f"{r['annual_pct']:.2f}",
          f"{r['t_stat']:.3f}", f"{r['max_dd_pct']:.2f}", f"{r['sharpe_per_obs']:.5f}"]
         for i, r in enumerate(best_dd, start=1)]))

    # --- 3. Копилка на 13 кандидатах -------------------------------------
    parts.append("\n## 3. 13 кандидатов с BTC-копилкой: расклад счёта\n")
    if cand13:
        rows = []
        for r in cand13:
            k = r["kopilka"]
            if k.get("status") != "OK":
                continue
            rows.append([
                r["id"], r["symbol"], r["risk"],
                f"{r['base']['annual_pct']:.2f}", f"{k['annual_pct']:.2f}",
                f"{r['delta_annual_pct']:+.2f}",
                f"{r['base']['max_dd_pct']:.2f}", f"{k['max_dd_pct']:.2f}",
                f"{k['final_btc_units']:.6f}", f"{k['final_btc_value']:.2f}",
                f"{k['final_asset_value']:.2f}", f"{k['final_value']:.2f}",
                f"{k['btc_share_pct']:.1f}", str(k["locks"]),
            ])
        parts.append(_table(
            ["ID", "Пара", "Риск", "База %/год", "С копилкой %/год", "Δ",
             "База DD %", "DD с копилкой %", "BTC, шт", "BTC в $", "Актив в $",
             "ВСЕГО в $", "Доля BTC %", "Фиксаций"],
            rows))
    else:
        parts.append("_Данных по 13 кандидатам пока нет._")

    # --- 4. Дефицит до цели ----------------------------------------------
    parts.append("\n## 4. Дефицит: чего не хватает измеренного до цели\n")
    parts.append(
        "Берём лучшую измеренную строку (по t при просадке <= 20%) и считаем, "
        "сколько ещё нужно %/год и какой просадки, чтобы дойти до цели за "
        "5 и 10 лет.\n")
    if best_dd:
        top = best_dd[0]
        annual = top["annual_pct"]
        dd = top["max_dd_pct"]
        rows = []
        for end, label in targets:
            for years in (5, 10):
                need = target_annual_pct(100.0, end, years)
                rows.append([
                    f"${end:,.0f}".replace(",", " "), label, str(years),
                    f"{need:.1f}%", f"{annual:.1f}%",
                    f"{need - annual:+.1f} п.п.",
                    f"{required_dd_for_target(annual, 100.0, end, years):.1f}%",
                    f"{growth_with_drawdown(annual, dd, years) * 100 - 100:.0f}%",
                ])
        parts.append(_table(
            ["Цель", "Название", "Лет", "Нужно %/год", "Есть %/год",
             "Дефицит", "Допустимая просадка при этой доходности",
             "Факт: рост с измеренной просадкой"],
            rows))
        parts.append(
            f"\nОпорная строка: {top['family']} / {top['symbol']} / {top['risk']} — "
            f"{annual:.2f}%/год, просадка {dd:.2f}%, t={top['t_stat']:.3f}.\n")

    # --- 5. Что из этого следует ----------------------------------------
    parts.append("## 5. Что из этого следует (конкретно)\n")
    best_annual = max((r["annual_pct"] for r in ok), default=0.0)
    best_annual_dd = min((r["max_dd_pct"] for r in ok if (r.get("annual_pct") or -999) == best_annual),
                          default=0.0)
    measured_max_dd20 = max((r["annual_pct"] for r in ok
                              if (r.get("max_dd_pct") or 999) <= 20.0), default=0.0)
    kop_best = max((r["kopilka"]["annual_pct"] for r in cand13
                    if r["kopilka"].get("status") == "OK"), default=0.0)
    rules = [
        ["Измеренный максимум годовой (любая просадка)",
         f"{best_annual:.1f}%", "5 лет, 34992 прогона"],
        ["Измеренный максимум годовой при просадке <= 20%",
         f"{measured_max_dd20:.1f}%", "5 лет, тот же скан"],
        ["Измеренный максимум с BTC-копилкой (13 кандидатов)",
         f"{kop_best:.1f}%", "5 лет, с раскладом счёта"],
        ["Требуется для $100 -> $1000 за 5 лет",
         f"{target_annual_pct(100.0, 1000.0, 5):.1f}%", "арифметика цели"],
        ["Требуется для $100 -> $100000 за 7 лет",
         f"{target_annual_pct(100.0, 100000.0, 7):.1f}%", "арифметика цели"],
    ]
    parts.append(_table(["Показатель", "Значение", "Источник"], rules))

    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    text = main()
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"written: {OUT}")
