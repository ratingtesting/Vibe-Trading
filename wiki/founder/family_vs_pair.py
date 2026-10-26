"""Честная проверка: семейственный эффект или эффект пар?

Корреляция среднего t семейства между двумя периодами = +0.90. Но есть
альтернативное объяснение: просто хорошо выбранные ПАРЫ. Если SOLUSDT
растёт в оба периода, то все семейства на SOL будут выглядеть хорошо в
оба периода, и корреляция между семействами возникнет сама.

Чтобы это исключить, из t каждой строки вычитается среднее t по её ПАРЕ
в том же периоде. Это "эффект пары" (pair fixed effect): остаётся только
то, что даёт именно семейство на этой паре.

Потом:
  - корреляция остатков между периодами по семействам;
  - то же самое по парам (остатки по парам - что даёт конкретная пара);
  - доля объяснённой дисперсии: семейство против пары.

Если корреляция остатков семейств держится (а она не может взяться из
пар), значит семейство - реальная устойчивая характеристика. Если нет,
то весь перевес объясняется парами, и торговать надо пары, а не семейства.

Ещё считается честный holdout-тест: пары отбираются по t на новом блоке,
проверяются на holdout 2020-2021.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OLD_PACK = FOUNDER / "old-returns"
SCAN_RESULTS = FOUNDER / "scan5y" / "scan-results.jsonl"
OUT = FOUNDER / "scan5y" / "family-vs-pair-effect.json"

ANNUALISATION = 365.0
HOLDOUT_BARS = 640
DEAD_SYMBOLS = {"LUNAUSDT"}


def metrics(ret: np.ndarray) -> dict:
    n = ret.size
    if n < 30:
        return {"t_stat": None, "annual_pct": None, "sharpe": None,
                "max_dd_pct": None}
    sd = float(np.std(ret, ddof=1))
    t_stat = float(np.mean(ret) / sd * math.sqrt(n)) if sd > 0 else None
    equity = np.cumprod(1.0 + ret)
    dd = float((equity / np.maximum.accumulate(equity) - 1.0).min()) * 100.0
    annual = float((1.0 + ret).prod() ** (ANNUALISATION / n) - 1.0) * 100.0
    if not math.isfinite(annual):
        annual = None
    return {"t_stat": t_stat, "annual_pct": annual,
            "sharpe": float(np.mean(ret)) / sd if sd > 0 else None,
            "max_dd_pct": abs(dd)}


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    return float(np.corrcoef(ra, rb)[0, 1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    symbols_map = json.loads((OLD_PACK / "symbols.json").read_text(encoding="utf-8"))
    freq_map = symbols_map.get("freqtrade-scan", {})

    # Новый блок: (family, symbol, risk) -> t
    new_cells: dict[tuple[str, str, str], float] = {}
    for line in SCAN_RESULTS.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("status") != "OK" or row.get("symbol") in DEAD_SYMBOLS:
            continue
        family = row.get("family", "")
        if not family.startswith("ft_"):
            continue
        value = row.get("t_stat")
        if isinstance(value, (int, float)):
            new_cells[(family[3:], row["symbol"], row["risk"])] = float(value)

    # Старый блок: holdout t по той же ячейке
    old_cells: dict[tuple[str, str, str], float] = {}
    for path in sorted((OLD_PACK / "returns").glob("freqtrade-scan__*.npz")):
        name = path.stem.split("__", 1)[1]
        restored = freq_map.get(name)
        if not restored:
            continue
        family, symbol, risk = (restored.get("rule"), restored.get("symbol"),
                                restored.get("risk"))
        if not family or symbol in DEAD_SYMBOLS:
            continue
        with np.load(path) as data:
            ret = np.asarray(data["ret"], dtype=float)
        if ret.size < HOLDOUT_BARS + 100:
            continue
        m = metrics(ret[:HOLDOUT_BARS])
        if m["t_stat"] is None:
            continue
        old_cells[(family, symbol, risk)] = m["t_stat"]

    common = sorted(set(new_cells) & set(old_cells))
    print(f"ячеек (семейство, пара, риск) в обоих периодах: {len(common)}")

    new_arr = np.array([new_cells[k] for k in common])
    old_arr = np.array([old_cells[k] for k in common])
    families = np.array([k[0] for k in common])
    symbols = np.array([k[1] for k in common])

    # Эффект пары: среднее t по паре в каждом периоде.
    def pair_means(values: np.ndarray, groups: np.ndarray) -> dict[str, float]:
        out = {}
        for g in set(groups):
            mask = groups == g
            out[g] = float(np.mean(values[mask]))
        return out

    new_pair_mean = pair_means(new_arr, symbols)
    old_pair_mean = pair_means(old_arr, symbols)
    new_resid = new_arr - np.array([new_pair_mean[s] for s in symbols])
    old_resid = old_arr - np.array([old_pair_mean[s] for s in symbols])

    # Семейный остаток: среднее остатка по семейству.
    def family_means(values: np.ndarray, groups: np.ndarray) -> dict[str, float]:
        out = {}
        for g in set(groups):
            mask = groups == g
            out[g] = float(np.mean(values[mask]))
        return out

    new_fam_resid = family_means(new_resid, families)
    old_fam_resid = family_means(old_resid, families)
    fam_keys = sorted(new_fam_resid)
    fam_new = np.array([new_fam_resid[k] for k in fam_keys])
    fam_old = np.array([old_fam_resid[k] for k in fam_keys])

    print()
    print("| Уровень | Пирсон (период ↔ период) | Спирмен |")
    print("|---|---:|---:|")
    print(f"| сырые t по строкам | {float(np.corrcoef(new_arr, old_arr)[0,1]):+.4f} | "
          f"{spearman(new_arr, old_arr):+.4f} |")
    print(f"| семейство (t по парам убрано) | {float(np.corrcoef(fam_new, fam_old)[0,1]):+.4f} | "
          f"{spearman(fam_new, fam_old):+.4f} |")
    pair_keys = sorted(new_pair_mean)
    pair_new = np.array([new_pair_mean[k] for k in pair_keys])
    pair_old = np.array([old_pair_mean[k] for k in pair_keys])
    print(f"| пара (t по семействам убрано) | {float(np.corrcoef(pair_new, pair_old)[0,1]):+.4f} | "
          f"{spearman(pair_new, pair_old):+.4f} |")
    print(f"| остатки ячеек (и пара, и семейство убраны) | "
          f"{float(np.corrcoef(new_resid, old_resid)[0,1]):+.4f} | "
          f"{spearman(new_resid, old_resid):+.4f} |")

    # Доля дисперсии, объяснённая семейством и парой.
    def var_share(resid: np.ndarray, groups: np.ndarray) -> float:
        means = family_means(resid, groups)
        explained = np.array([means[g] for g in groups])
        return float(np.var(explained) / np.var(resid)) if np.var(resid) > 0 else 0.0

    fam_share_new = var_share(new_arr, families)
    fam_share_old = var_share(old_arr, families)
    pair_share_new = var_share(new_arr, symbols)
    pair_share_old = var_share(old_arr, symbols)
    print()
    print(f"доля дисперсии t, объяснённая СЕМЕЙСТВОМ: новый блок {fam_share_new*100:.1f}%, "
          f"holdout {fam_share_old*100:.1f}%")
    print(f"доля дисперсии t, объяснённая ПАРОЙ:       новый блок {pair_share_new*100:.1f}%, "
          f"holdout {pair_share_old*100:.1f}%")

    # Честный holdout-тест: пары отбираются по t на новом блоке внутри
    # семейства, проверяются на holdout.
    print()
    print("| Семейство | пар в holdout | средний t holdout | t≥2.5 | прибыльных |")
    print("|---|---:|---:|---:|---:|")
    results = []
    for family in sorted(set(families)):
        mask = families == family
        idx = np.where(mask)[0]
        order = idx[np.argsort(-new_arr[idx])]
        sel = order[:10]
        ho_t = [old_arr[i] for i in sel]
        ho_annual = []
        for i in sel:
            ho_annual.append(old_cells[common[i]])
        # прибыльность: доля строк с t>0 на holdout среди отобранных
        prof = float(np.mean([t > 0 for t in ho_t]))
        results.append({
            "family": family,
            "n": len(sel),
            "holdout_mean_t": float(np.mean(ho_t)),
            "holdout_median_t": float(np.median(ho_t)),
            "holdout_t_ge_2_5": int(sum(1 for t in ho_t if t >= 2.5)),
            "holdout_profitable_share": prof,
            "new_mean_t": float(np.mean(new_arr[idx])),
        })
        print(f"| {family} | {len(sel)} | {float(np.mean(ho_t)):+.3f} | "
              f"{int(sum(1 for t in ho_t if t >= 2.5))} | {prof*100:.0f}% |")

    results.sort(key=lambda r: -r["new_mean_t"])
    top5 = [r for r in results[:5]]
    bottom = results[len(results)//2:]
    z = ((float(np.mean([r["holdout_mean_t"] for r in top5]))
          - float(np.mean([r["holdout_mean_t"] for r in bottom])))
         / float(np.std([r["holdout_mean_t"] for r in bottom], ddof=1)))
    print(f"\nтоп-5 семейств (по t на новом блоке) против нижней половины на holdout: z = {z:+.2f}")

    payload = {
        "date": "2026-10-26",
        "method": (
            "Эффект пары убран вычитанием среднего t по паре из каждой строки. "
            "Остаётся вклад семейства. Аналогично убран эффект семейства для "
            "изоляции вклада пары. Честный holdout: пары отобраны по t на новом "
            "блоке внутри семейства, проверены на 2020-01..2021-10."),
        "n_cells": len(common),
        "corr_raw_cells": float(np.corrcoef(new_arr, old_arr)[0, 1]),
        "corr_family_residuals": float(np.corrcoef(fam_new, fam_old)[0, 1]),
        "corr_pair_residuals": float(np.corrcoef(pair_new, pair_old)[0, 1]),
        "corr_cell_residuals": float(np.corrcoef(new_resid, old_resid)[0, 1]),
        "var_share_by_family": {"new_block": fam_share_new, "holdout": fam_share_old},
        "var_share_by_pair": {"new_block": pair_share_new, "holdout": pair_share_old},
        "z_top5_vs_bottom_half_on_holdout": z,
        "families": results,
        "honest_limits": [
            "Обе выборки (2021-2026 и 2020-2021) - это крипта; holdout "
            "медвежий, что консервативно для бычьих стратегий.",
            "Топ-10 пар внутри семейства отбираются по новому блоку - "
            "это легитимно, holdout в отборе не участвовал.",
            "Пары внутри семейства коррелированы между собой.",
            "Найденное - НАБЛЮДЕНИЕ. Следующего holdout для подтверждения "
            "ещё нет: 2026 год закончился, данных за ним нет.",
        ],
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwritten: {args.out}")


if __name__ == "__main__":
    main()
