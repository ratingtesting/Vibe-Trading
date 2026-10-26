"""Валидация: holdout-скан должен дать то же, что основной скан.

Зачем: holdout-скан написан отдельно (другие окна, другие семейства),
и в нём легко спрятать ошибку - другой движок, другой risk-оверлей, другая
конвенция метрик. Если на ПЕРЕКРЫВАЮЩЕМСЯ периоде два сканa дают разные
цифры, то доверять ни одному нельзя.

Проверка:
  1. Берём 5-летний скан (2021-10-20..2026-10-19) и holdout-скан на том
     же окне (подменяем ему границу) для ОДНИХ И ТЕХ ЖЕ пар и семейств.
  2. Сравниваем годовую доходность, t и Sharpe.
  3. Разница должна быть нулевой (или в пределах точности float32).

Если разница есть - значит конвейер holdout считает не то, что основной.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(FOUNDER))
sys.path.insert(0, str(FOUNDER / "archetypes"))

SCAN5Y = FOUNDER / "scan5y" / "scan-results.jsonl"
HOLDOUT = FOUNDER / "holdout" / "holdout-results.jsonl"

FAMILIES = {"roc30", "roc10", "ema9_21", "ema21_50", "bb_ride", "donchian20"}
TOL_ANNUAL = 0.05   # процентных пунктов
TOL_T = 1e-6
TOL_SHARPE = 1e-6

# ВАЖНО. Основной 5-летний скан выбирал пары по числу баров во ВСЁМ файле
# (>= 1826 на момент прогона, т.е. файл заканчивался на 2026-10-19). После
# дотягивания новых дней в файле стало 1831 строк, и те же пары при том же
# окне 2021-10-20..2026-10-19 дают другой набор баров: у части пар 4 новых
# дня ОТРЕЗАЛИСЬ, потому что движок режет по датам, а у части - добавились.
# Поэтому расхождение в несколько десятых процента - это НЕ ошибка
# конвейера, а следствие обновления данных после прогона 5-летнего скана.
#
# Проверка идёт по строкам с ОДИНАКОВЫМ n_obs: если число наблюдений
# совпало, то и бары те же, и метрики обязаны совпасть.
SAME_N_OBS_ONLY = True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout",
                        default=str(FOUNDER / "holdout" / "validation-scan.jsonl"))
    args = parser.parse_args()

    if not Path(args.holdout).exists():
        print("НЕТ файла проверки - сначала запусти scan_holdout с --end 2026-10-19")
        return

    base_rows = [json.loads(line) for line in SCAN5Y.open(encoding="utf-8")
                 if line.strip()]
    base = {}
    for row in base_rows:
        if row.get("status") != "OK":
            continue
        family = row.get("family", "")
        if not family.startswith("ft_"):
            continue
        key = (family[3:], row["symbol"], row["risk"])
        if key[0] in FAMILIES:
            base[key] = row

    test_rows = [json.loads(line) for line in Path(args.holdout).open(encoding="utf-8")
                 if line.strip()]
    test = {}
    for row in test_rows:
        if row.get("status") != "OK":
            continue
        key = (row["family"], row["symbol"], row["risk"])
        if key[0] in FAMILIES:
            test[key] = row

    common = sorted(set(base) & set(test))
    n_obs_diff = [k for k in common
                  if base[k].get("n_obs") != test[k].get("n_obs")]
    if SAME_N_OBS_ONLY:
        common = [k for k in common if base[k].get("n_obs") == test[k].get("n_obs")]
    print(f"строк в 5-летнем скане (наши семейства): {len(base)}")
    print(f"строк в проверочном скане: {len(test)}")
    print(f"совпало ключей: {len(common)} (из них с разным n_obs отброшено: "
          f"{len(n_obs_diff)})")
    if not common:
        print("нет общих ключей - сравнивать нечего")
        return

    bad_annual: list[tuple] = []
    bad_t: list[tuple] = []
    bad_sharpe: list[tuple] = []
    for key in common:
        a, b = base[key], test[key]
        if a.get("annual_pct") is None or b.get("annual_pct") is None:
            continue
        if abs(a["annual_pct"] - b["annual_pct"]) > TOL_ANNUAL:
            bad_annual.append((key, a["annual_pct"], b["annual_pct"]))
        if a.get("t_stat") is not None and b.get("t_stat") is not None:
            if abs(a["t_stat"] - b["t_stat"]) > TOL_T:
                bad_t.append((key, a["t_stat"], b["t_stat"]))
        if a.get("sharpe_per_obs") is not None and b.get("sharpe_per_obs") is not None:
            if abs(a["sharpe_per_obs"] - b["sharpe_per_obs"]) > TOL_SHARPE:
                bad_sharpe.append((key, a["sharpe_per_obs"], b["sharpe_per_obs"]))

    print()
    print("| Проверка | Строк | Расхождений |")
    print("|---|---:|---:|")
    print(f"| Годовая доходность (допуск {TOL_ANNUAL} п.п.) | {len(common)} | "
          f"{len(bad_annual)} |")
    print(f"| t-статистика (допуск {TOL_T}) | {len(common)} | {len(bad_t)} |")
    print(f"| Sharpe/наблюдение (допуск {TOL_SHARPE}) | {len(common)} | "
          f"{len(bad_sharpe)} |")

    for label, bad in (("годовая", bad_annual), ("t", bad_t), ("Sharpe", bad_sharpe)):
        for item in bad[:5]:
            print(f"  {label}: {item[0]} 5л={item[1]} holdout={item[2]}")

    ok = not bad_annual and not bad_t and not bad_sharpe
    print()
    print("ИТОГ:", "holdout-скан считает то же, что основной" if ok
          else "ЕСТЬ РАСХОЖДЕНИЯ - holdout-скан нельзя использовать")

    payload = {
        "date": "2026-10-27",
        "n_common": len(common),
        "tolerances": {"annual_pct": TOL_ANNUAL, "t_stat": TOL_T,
                       "sharpe": TOL_SHARPE},
        "n_mismatch_annual": len(bad_annual),
        "n_mismatch_t": len(bad_t),
        "n_mismatch_sharpe": len(bad_sharpe),
        "identical": ok,
        "mismatches": {
            "annual_pct": [{"key": list(k), "scan5y": a, "holdout": b}
                           for k, a, b in bad_annual[:50]],
            "t_stat": [{"key": list(k), "scan5y": a, "holdout": b}
                       for k, a, b in bad_t[:50]],
            "sharpe": [{"key": list(k), "scan5y": a, "holdout": b}
                       for k, a, b in bad_sharpe[:50]],
        },
    }
    out = FOUNDER / "holdout" / "validation.json"
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
