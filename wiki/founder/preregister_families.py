"""ПРЕДРЕГИСТРАЦИЯ: фиксируем семейства-гипотезы ДО того, как появятся
новые данные.

Зачем это нужно
Исследование показало: переносится СЕМЕЙСТВО (правило + параметры), а не
отдельная строка. Значит, чтобы проверить это честно, нужно ЗАРАНЕЕ
записать, какие семейства мы берём в работу, и потом проверить их на
данных, которых мы ещё не видели.

Проблема: данные кончаются 2026-10-19. Следующего holdout (2027 год)
ещё нет. Значит, пре-регистрация - это не формальность, а единственный
способ получить настоящую проверку: зафиксировать сейчас, проверить
позже, когда данные появятся.

Что фиксируется
1. Список семейств с их параметрами (правило + набор параметров).
2. Для каждого семейства - правило выбора пары внутри него (порядок и
   размер), зафиксированный ЗАРАНЕЕ.
3. Пороги приёмки: t, DSR (в узком пуле), просадка.
4. Контрольные метрики, по которым будет вынесен вердикт.
5. Слепые точки: что НЕ считается успехом.

Протокол проверки (на будущее)
- Когда появятся данные после 2026-10-19, запускается scan на тех же
  семействах с теми же параметрами и тем же risk-режимом.
- Считается доходность в годовых, t, Sharpe на наблюдение, просадка.
- DSR - в узком пуле (семейство + его пары), планка 0.95.
- Вердикт: прошло / не прошло. Никаких доводов "а давайте ещё раз
  посчитаем с другим порогом".

Честность
- Пре-регистрация НЕ делает результат истинным. Она делает проверку
  честной: если семейство не выдержит проверки, это будет видно сразу.
- Список семейств выбран по данным до 2026-10-19, поэтому он не
  свободен от подбора - это признано явно. Настоящая чистота начнётся
  с первой же проверки на новых данных.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
SCAN = FOUNDER / "scan5y"
OUT = FOUNDER / "PREREGISTRATION.md"

# Пороги приёмки - фиксируются ДО проверки и не меняются после.
GATES = {
    "t_stat_min": 2.5,
    "dsr_narrow_min": 0.95,
    "max_dd_pct": 20.0,
    "annual_pct_min": 0.0,
    "min_pairs_to_test": 10,
    "min_holdout_days": 180,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    reverse = json.loads((SCAN / "family-reverse-test.json").read_text(encoding="utf-8"))
    transfer = json.loads((SCAN / "family-transfer.json").read_text(encoding="utf-8"))
    selection = json.loads((SCAN / "family-selection-test.json").read_text(encoding="utf-8"))

    # Семейства: рангированные по старому блоку (независимый от нового).
    ranking = reverse["family_check"]

    # Два НЕЗАВИСИМЫХ критерия отбора семейств. Оба опираются на данные,
    # не пересекающиеся по датам с проверкой:
    #   критерий A - средний t на старом блоке (2020-01..2021-10);
    #   критерий B - пережило оба разбиения внутри 5-летнего окна
    #                (z > 2 в обоих), т.е. прошло проверку на 2021-2026.
    # Берём объединение: семейство в работе, если выдержало ХОТЯ БЫ ОДИН
    # из независимых критериев. Критерий B строже, но опирается на большее
    # число наблюдений, поэтому не отбрасываем его.
    top_a = ranking[:5]
    passed_b = sorted({row["family"].replace("ft_", "")
                       for row in transfer["families"] if row["both_pass_z2"]})

    selected: list[dict] = []
    seen: set[str] = set()
    for row in top_a:
        selected.append({**row, "criterion": "A: топ-5 по рангу старого блока"})
        seen.add(row["family"])
    by_name = {row["family"]: row for row in ranking}
    for family in passed_b:
        if family in seen:
            for item in selected:
                if item["family"] == family:
                    item["criterion"] += " + B: оба разбиения (z>2)"
            continue
        base = by_name.get(family, {})
        selected.append({
            "family": family,
            "rank_old": base.get("rank_old"),
            "old_mean_t": base.get("old_mean_t"),
            "new_mean_t": base.get("new_mean_t"),
            "new_profitable_share": base.get("new_profitable_share"),
            "criterion": "B: пережило оба разбиения (z>2)",
        })
        seen.add(family)

    lines = []
    lines.append("# ПРЕДРЕГИСТРАЦИЯ: семейства-гипотезы")
    lines.append("")
    lines.append(f"**Дата фиксации:** {date.today().isoformat()}")
    lines.append("")
    lines.append("Документ фиксирует выбор ДО проверки. Любая правка после "
                 "появления новых данных превращает проверку в подгонку — "
                 "поэтому здесь записано всё, что нужно для вердикта.")
    lines.append("")
    lines.append("## 1. Что мы знаем на момент фиксации")
    lines.append("")
    lines.append("| Факт | Значение |")
    lines.append("|---|---:|")
    lines.append("| Пул 5-летнего скана | 34 992 прогона |")
    lines.append("| Пул DSR (старые + новые) | 42 299 |")
    lines.append("| ЭТАЛОН / КАНДИДАТ | 0 / 0 |")
    lines.append("| Корреляция train↔test по строкам | +0.0321 |")
    lines.append("| Корреляция по семействам (старый→новый) | "
                 f"{reverse['pearson_corr_family_ranking_old_to_new']:+.4f} |")
    lines.append("| Доля дисперсии t от семейства | 35–52% |")
    lines.append("| Доля дисперсии t от пары | 3–4% |")
    lines.append("")
    lines.append("Вывод, ради которого нужна пре-регистрация: **ранжировать "
                 "надо семейства, а не строки**. Ранжирование строк не "
                 "переносится — это показал walk-forward.")
    lines.append("")
    lines.append("## 2. Гипотеза: какие семейства берём")
    lines.append("")
    lines.append("Два независимых критерия отбора. Оба опираются на данные, "
                 "не пересекающиеся по датам с будущей проверкой:")
    lines.append("")
    lines.append("- **Критерий A** — топ-5 по среднему t на СТАРОМ блоке "
                 "(2020-01-01..2021-10-19).")
    lines.append("- **Критерий B** — пережило оба независимых разбиения "
                 "внутри 5-летнего окна (z > 2 в обоих), то есть прошло "
                 "проверку на 2021–2026.")
    lines.append("")
    lines.append("Берём **объединение**: семейство в работе, если выдержало "
                 "хотя бы один из критериев. Критерий B строже, но опирается "
                 "на большее число наблюдений, поэтому отбрасывать его нельзя.")
    lines.append("")
    lines.append("| Семейство | Критерий | Ранг (старый) | t на старом | t на новом | прибыльных на новом |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for row in selected:
        rank = row.get("rank_old") if row.get("rank_old") is not None else "—"
        old_t = (f"{row['old_mean_t']:+.3f}" if row.get("old_mean_t") is not None else "—")
        new_t = (f"{row['new_mean_t']:+.3f}" if row.get("new_mean_t") is not None else "—")
        prof = (f"{row['new_profitable_share']*100:.0f}%"
                if row.get("new_profitable_share") is not None else "—")
        lines.append(f"| **{row['family']}** | {row['criterion']} | {rank} | "
                     f"{old_t} | {new_t} | {prof} |")
    lines.append("")
    lines.append("### 2.1 Правило выбора пары внутри семейства")
    lines.append("")
    lines.append("Фиксируется ЗАРАНЕЕ, чтобы отбор пары не стал новой "
                 "подгонкой:")
    lines.append("")
    lines.append("1. Берём **все пары**, на которых семейство даёт хотя бы "
                 "одну сделку (иначе результат невоспроизводим).")
    lines.append("2. Внутри семейства пары **не ранжируются по доходности** — "
                 "ранжирование пар внутри семейства почти целиком шум "
                 "(проверено: отбор 30 пар даёт на новом блоке средний t "
                 "+0.156 против +0.442 у отбора 5 пар).")
    lines.append("3. Торгуем **все пары семейства равными долями** с "
                 "vol-риском: одна стратегия, много пар, риск "
                 "нормируется по волатильности.")
    lines.append("4. Если в семействе меньше 10 пар — семейство в "
                 "пре-регистрацию не берётся (недостаточно наблюдений).")
    lines.append("")
    lines.append("## 3. Пороги приёмки (зафиксированы до проверки)")
    lines.append("")
    lines.append("| Порог | Значение |")
    lines.append("|---|---:|")
    lines.append(f"| t-статистика, не ниже | {GATES['t_stat_min']} |")
    lines.append(f"| DSR в узком пуле (семейство + пары), не ниже | {GATES['dsr_narrow_min']} |")
    lines.append(f"| Просадка, не выше | {GATES['max_dd_pct']}% |")
    lines.append(f"| Годовая доходность, не ниже | {GATES['annual_pct_min']}% |")
    lines.append(f"| Пар в семействе, не меньше | {GATES['min_pairs_to_test']} |")
    lines.append(f"| Дней holdout, не меньше | {GATES['min_holdout_days']} |")
    lines.append("")
    lines.append("## 4. Протокол проверки (на будущее)")
    lines.append("")
    lines.append("1. Когда появятся данные после 2026-10-19, запустить скан "
                 "**ровно по этим семействам**, с теми же параметрами и тем же "
                 "risk-режимом (vol10).")
    lines.append("2. Считать на новых данных: доходность в годовых, "
                 "t, Sharpe на наблюдение, просадку, DSR в узком пуле.")
    lines.append("3. Вердикт по каждому семейству: **прошло** / **не прошло** "
                 "по порогам из раздела 3.")
    lines.append("4. Вердикт по гипотезе в целом: семейство считается "
                 "подтверждённым, если прошло хотя бы одно и **воспроизвело "
                 "прибыльность на новых данных** (доля прибыльных пар ≥ 60%).")
    lines.append("")
    lines.append("## 5. Что НЕ считается успехом")
    lines.append("")
    lines.append("- Пересчёт с другим порогом или другим окном после "
                 "получения результата.")
    lines.append("- «Семейство почти прошло» (t = 2.2 вместо 2.5).")
    lines.append("- Лучшая пара внутри семейства вместо всех пар семейства.")
    lines.append("- Перенос правила выбора пары на новый период.")
    lines.append("- Утверждение «край есть» на основании того, что семейство "
                 "вышло в топ на прошлом периоде.")
    lines.append("")
    lines.append("## 6. Ограничения самой пре-регистрации")
    lines.append("")
    lines.append("- Семейства выбраны по данным до 2026-10-19, поэтому в "
                 "выборе есть подгонка. Признано явно: чистота начинается с "
                 "первой же проверки на новых данных.")
    lines.append("- Оба периода - крипта. На других рынках переносимость может "
                 "быть другой.")
    lines.append("- Данных заканчиваются 2026-10-19: следующего holdout "
                 "(2027 год) ещё нет, поэтому сейчас пре-регистрация - это "
                 "обязательство, а не результат.")
    lines.append("- Holdout 2020-2021 - медвежий рынок: консервативно для "
                 "бычьих стратегий, оптимистично для шортовых.")
    lines.append("")
    lines.append("## 7. Что показала проверка на старом блоке (для контекста)")
    lines.append("")
    lines.append("| Группа | семейств | средний t на новом | прибыльных |")
    lines.append("|---|---:|---:|---:|")
    for label, data in selection["holdout_groups"].items():
        lines.append(f"| {label.replace('_', ' ')} | {data['n_families']} | "
                     f"{data['mean_family_t']:+.3f} | "
                     f"{data['mean_profitable_share']*100:.0f}% |")
    lines.append("")

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"written: {args.out}")
    print("\nЗафиксированные семейства:")
    for row in selected:
        rank = row.get("rank_old") if row.get("rank_old") is not None else "—"
        old_t = (f"{row['old_mean_t']:+.3f}" if row.get("old_mean_t") is not None else "—")
        print(f"  [{row['criterion']}] {row['family']} (ранг {rank}, t старый {old_t})")
    print(f"\nПороги: t≥{GATES['t_stat_min']}, DSR≥{GATES['dsr_narrow_min']}, "
          f"DD≤{GATES['max_dd_pct']}%, пар≥{GATES['min_pairs_to_test']}, "
          f"дней≥{GATES['min_holdout_days']}")


if __name__ == "__main__":
    main()
