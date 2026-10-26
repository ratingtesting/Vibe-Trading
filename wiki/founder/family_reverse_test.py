"""Обратная проверка: ранжирование семейств по СТАРОМУ блоку -> проверка
на НОВОМ.

Предыдущие шаги ранжировали семейства по новому блоку (2021-10..2026-10) и
проверяли на holdout 2020-01..2021-10. Это честно, но ранжирование всё
равно делалось на более свежих данных, а проверка - на более старых.

Настоящая независимость требует обратного: ранжировать по СТАРОМУ блоку
и проверять на НОВОМ. Если семейство реально устойчиво, то семейства,
лидирующие на старом блоке, должны лидировать и на новом.

Ещё одна вещь, которую надо проверить: сколько пар на самом деле нужно
внутри семейства. Если достаточно топ-5 пар, то отбор почти не шумит.
Если нужно топ-30, то внутрисемейный отбор всё ещё шумный и вся схема
не работает.

И третье: честный DSR в узком пуле (семейство + его пары) - сколько
кандидатов проходят гейт DSR>=0.95.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OLD_PACK = FOUNDER / "old-returns"
SCAN_RESULTS = FOUNDER / "scan5y" / "scan-results.jsonl"
OUT = FOUNDER / "scan5y" / "family-reverse-test.json"

sys.path.insert(0, str(REPO))
from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

ANNUALISATION = 365.0
HOLDOUT_BARS = 640
DEAD_SYMBOLS = {"LUNAUSDT"}
TOP_PAIRS = (5, 10, 20, 30)


def metrics(ret: np.ndarray) -> dict:
    n = ret.size
    if n < 30:
        return {"t_stat": None, "annual_pct": None, "sharpe": None}
    sd = float(np.std(ret, ddof=1))
    t_stat = float(np.mean(ret) / sd * math.sqrt(n)) if sd > 0 else None
    annual = float((1.0 + ret).prod() ** (ANNUALISATION / n) - 1.0) * 100.0
    if not math.isfinite(annual):
        annual = None
    return {"t_stat": t_stat, "annual_pct": annual,
            "sharpe": float(np.mean(ret)) / sd if sd > 0 else None}


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

    # Старый блок: holdout-метрики по (семейство, пара, риск).
    old_cells: dict[tuple[str, str, str], dict] = {}
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
        old_cells[(family, symbol, risk)] = metrics(ret[:HOLDOUT_BARS])

    # Новый блок: метрики по той же ячейке.
    new_cells: dict[tuple[str, str, str], dict] = {}
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
        new_cells[(family[3:], row["symbol"], row["risk"])] = row

    common = sorted(set(old_cells) & set(new_cells))
    print(f"общих ячеек: {len(common)}")

    families = sorted({k[0] for k in common})

    # Ранжирование ТОЛЬКО по старому блоку.
    old_family_t = {}
    for family in families:
        vals = [old_cells[(family, s, r)]["t_stat"] for (f, s, r) in common
                if f == family and old_cells[(family, s, r)]["t_stat"] is not None]
        old_family_t[family] = float(np.mean(vals))
    order = sorted(families, key=lambda f: -old_family_t[f])
    print("ранжирование по старому блоку:")
    for rank, family in enumerate(order, 1):
        print(f"  {rank:2d}. {family:20s} t={old_family_t[family]:+.3f}")

    # Проверка на новом блоке.
    print()
    print("| Ранг (по старому) | Семейство | t на старом | t на новом | прибыльных на новом |")
    print("|---:|---|---:|---:|---:|")
    family_check = []
    for rank, family in enumerate(order, 1):
        vals = [new_cells[(family, s, r)] for (f, s, r) in common if f == family]
        t_new = [v["t_stat"] for v in vals if isinstance(v.get("t_stat"), (int, float))]
        ann = [v["annual_pct"] for v in vals
               if isinstance(v.get("annual_pct"), (int, float))]
        prof = sum(1 for x in ann if x > 0) / len(ann) if ann else 0.0
        family_check.append({
            "rank_old": rank, "family": family,
            "old_mean_t": old_family_t[family],
            "new_mean_t": float(np.mean(t_new)),
            "new_profitable_share": prof,
        })
        print(f"| {rank} | {family} | {old_family_t[family]:+.3f} | "
              f"{float(np.mean(t_new)):+.3f} | {prof*100:.0f}% |")

    old_arr = np.array([old_family_t[f] for f in order])
    new_arr = np.array([c["new_mean_t"] for c in family_check])
    pearson = float(np.corrcoef(old_arr, new_arr)[0, 1])
    spear = spearman(old_arr, new_arr)
    print(f"\nкорреляция ранжирования семейств (старый -> новый): "
          f"Пирсон {pearson:+.4f}, Спирмен {spear:+.4f}")

    # Сколько пар нужно внутри семейства.
    print()
    print("| Топ-K пар внутри семейства (отбор по старому) | семейств | средний t на новом | t≥2.5 | прибыльных |")
    print("|---|---:|---:|---:|---:|")
    pair_table = {}
    for k in TOP_PAIRS:
        t_vals, prof_vals, g25 = [], [], 0
        for family in order:
            idx = [(s, r) for (f, s, r) in common
                   if f == family and old_cells[(family, s, r)]["t_stat"] is not None]
            idx.sort(key=lambda sr: -old_cells[(family, sr[0], sr[1])]["t_stat"])
            sel = idx[:k]
            ts = [new_cells[(family, s, r)].get("t_stat") for s, r in sel]
            ts = [t for t in ts if isinstance(t, (int, float))]
            anns = [new_cells[(family, s, r)].get("annual_pct") for s, r in sel]
            anns = [a for a in anns if isinstance(a, (int, float))]
            if not ts:
                continue
            t_vals.extend(ts)
            prof_vals.append(sum(1 for a in anns if a > 0) / len(anns) if anns else 0.0)
            g25 += sum(1 for t in ts if t >= 2.5)
        pair_table[f"top_{k}_pairs"] = {
            "mean_t_on_new": float(np.mean(t_vals)),
            "rows_t_ge_2_5": g25,
            "mean_family_profitable": float(np.mean(prof_vals)),
        }
        print(f"| топ-{k} пар | {len(families)} семейств | {float(np.mean(t_vals)):+.3f} | "
              f"{g25} | {float(np.mean(prof_vals))*100:.0f}% |")

    # Честный DSR в узком пуле: семейство + его пары (только новый блок).
    narrow = []
    for family in order:
        idx = [(s, r) for (f, s, r) in common if f == family]
        sharpes = [new_cells[(family, s, r)]["sharpe_per_obs"] for s, r in idx
                   if isinstance(new_cells[(family, s, r)].get("sharpe_per_obs"), (int, float))]
        if len(sharpes) < 20:
            continue
        sd = st.stdev(sharpes)
        ranked = sorted(
            [(new_cells[(family, s, r)], s, r) for s, r in idx
             if isinstance(new_cells[(family, s, r)].get("sharpe_per_obs"), (int, float))],
            key=lambda x: -x[0]["sharpe_per_obs"])
        best, symbol, risk = ranked[0]
        try:
            res = deflated_sharpe_ratio(
                observed_sharpe=best["sharpe_per_obs"], n_trials=len(sharpes),
                n_observations=best["n_obs"], trial_sharpe_std=sd,
                skew=best.get("skew") or 0.0, kurtosis=best.get("kurtosis") or 3.0)
            dsr = float(res.deflated_sharpe_ratio)
            sr_star = float(res.expected_maximum_sharpe)
        except Exception:
            continue
        narrow.append({
            "family": family, "family_rank_old": order.index(family) + 1,
            "narrow_pool": len(sharpes),
            "symbol": symbol, "risk": risk,
            "annual_pct": best["annual_pct"], "t_stat": best["t_stat"],
            "max_dd_pct": best["max_dd_pct"],
            "sharpe_per_obs": best["sharpe_per_obs"],
            "dsr_narrow": dsr, "sr_star_narrow": sr_star,
            "passes_narrow_gate": dsr >= 0.95 and (best["t_stat"] or 0) >= 2.5
                                  and abs(best["max_dd_pct"] or 999) <= 20.0,
            "holdout_t_of_family": old_family_t[family],
        })

    print()
    print("| Семейство | Ранг по старому | Пара | Риск | %/год | t | DD % | Sharpe | DSR узкий | SR* | Гейт |")
    print("|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|")
    for row in narrow:
        print(f"| {row['family']} | {row['family_rank_old']} | {row['symbol']} | "
              f"{row['risk']} | {row['annual_pct']:.2f} | {row['t_stat']:.3f} | "
              f"{row['max_dd_pct']:.2f} | {row['sharpe_per_obs']:.5f} | "
              f"{row['dsr_narrow']:.4f} | {row['sr_star_narrow']:.5f} | "
              f"{'ДА' if row['passes_narrow_gate'] else 'нет'} |")

    payload = {
        "date": "2026-10-26",
        "method": (
            "Ранжирование семейств по среднему t на СТАРОМ блоке "
            "(holdout 2020-01..2021-10), проверка на НОВОМ блоке "
            "(2021-10..2026-10). Полностью обратный порядок относительно "
            "предыдущего теста."),
        "n_cells": len(common),
        "n_families": len(families),
        "pearson_corr_family_ranking_old_to_new": pearson,
        "spearman_corr_family_ranking_old_to_new": spear,
        "family_check": family_check,
        "pairs_inside_family": pair_table,
        "narrow_dsr": narrow,
        "n_narrow_pass": sum(1 for row in narrow if row["passes_narrow_gate"]),
        "honest_limits": [
            "Оба периода - крипта; они перекрываются по времени частично "
            "(старый блок идёт до 2026-10), поэтому полной независимости нет.",
            "Старый блок имеет только 30 пар, новый - 144: часть пар "
            "проверяется на более коротком ряду.",
            "Внутрисемейный отбор пар тоже шумит: показано, сколько пар "
            "нужно, чтобы результат был устойчивым.",
            "DSR в узком пуле честен только при зафиксированном заранее "
            "семействе - здесь семейство выбрано по старому блоку, а "
            "проверяется на новом, что и требуется.",
        ],
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwritten: {args.out}")
    print(f"прошли узкий гейт (DSR>=0.95, t>=2.5, DD<=20%): "
          f"{sum(1 for row in narrow if row['passes_narrow_gate'])}")


if __name__ == "__main__":
    main()
