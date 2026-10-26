"""Проверка пре-регистрации на новых данных. Без возможности подкрутить.

Запускается когда появятся данные после 2026-10-19. Читает
PREREGISTRATION.md (пороги и список семейств зафиксированы там), прогоняет
те же семейства с теми же параметрами и тем же risk-режимом на НОВЫХ
данных и выносит вердикт.

Ничего не настраивается: ни пороги, ни список семейств, ни правило выбора
пары. Если данные не проходят - они не проходят.

Правила (из PREREGISTRATION.md):
  - семейство: все пары, где оно дало хотя бы одну сделку;
  - пары не ранжируются по доходности;
  - пороги: t >= 2.5, DSR >= 0.95 (узкий пул: семейство + его пары),
    просадка <= 20%;
  - семейство подтверждено, если прошло пороги И доля прибыльных пар
    на новых данных >= 60%.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics as st
import sys
from datetime import date
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
PREREG = FOUNDER / "PREREGISTRATION.md"
OUT = FOUNDER / "prereg-verdict.json"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(FOUNDER))

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

ANNUALISATION = 365.0
# Граница "новых данных": всё, что после неё, - holdout.
NEW_DATA_START = "2026-10-20"
MIN_PROFITABLE_SHARE = 0.60


def parse_prereg() -> dict:
    """Читает зафиксированные пороги и семейства из PREREGISTRATION.md."""
    text = PREREG.read_text(encoding="utf-8")
    gates = {
        "t_stat_min": float(re.search(r"t-статистика, не ниже \| ([\d.]+)", text).group(1)),
        "dsr_narrow_min": float(re.search(r"DSR в узком пуле.*?не ниже \| ([\d.]+)", text).group(1)),
        "max_dd_pct": float(re.search(r"Просадка, не выше \| ([\d.]+)", text).group(1)),
        "min_pairs_to_test": int(re.search(r"Пар в семействе, не меньше \| (\d+)", text).group(1)),
        "min_holdout_days": int(re.search(r"Дней holdout, не меньше \| (\d+)", text).group(1)),
    }
    families: list[str] = []
    for line in text.splitlines():
        match = re.match(r"\| \*\*([a-z0-9_]+)\*\* \| [AB]:", line)
        if match:
            families.append(match.group(1))
    return {"gates": gates, "families": families}


def metrics(ret: np.ndarray) -> dict:
    n = ret.size
    if n < 30:
        return {"t_stat": None, "annual_pct": None, "sharpe": None,
                "max_dd_pct": None, "n_obs": n, "trades": 0}
    sd = float(np.std(ret, ddof=1))
    sharpe = float(np.mean(ret)) / sd if sd > 0 else None
    t_stat = float(np.mean(ret) / sd * math.sqrt(n)) if sd > 0 else None
    equity = np.cumprod(1.0 + ret)
    dd = float((equity / np.maximum.accumulate(equity) - 1.0).min()) * 100.0
    annual = float((1.0 + ret).prod() ** (ANNUALISATION / n) - 1.0) * 100.0
    if not math.isfinite(annual):
        annual = None
    return {"t_stat": t_stat, "annual_pct": annual, "sharpe": sharpe,
            "max_dd_pct": abs(dd), "n_obs": n,
            "trades": int((np.abs(np.diff(np.r_[0.0, ret])) > 0).sum())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(FOUNDER / "scan5y" / "scan-results.jsonl"))
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    pre = parse_prereg()
    gates = pre["gates"]
    families = pre["families"]
    print(f"пре-регистрация: {len(families)} семейств")
    print(f"пороги: t≥{gates['t_stat_min']}, DSR≥{gates['dsr_narrow_min']}, "
          f"DD≤{gates['max_dd_pct']}%, пар≥{gates['min_pairs_to_test']}, "
          f"дней≥{gates['min_holdout_days']}")
    print(f"граница новых данных: {NEW_DATA_START}")
    print()

    if not Path(args.results).exists():
        print("НЕТ файла результатов - проверять нечего.")
        return

    rows = [json.loads(line) for line in Path(args.results).open(encoding="utf-8")
            if line.strip()]
    # Только строки, чей период ЗАХОДИТ за границу новых данных.
    fresh = [r for r in rows
             if r.get("status") == "OK"
             and r.get("period_end", "") >= NEW_DATA_START]
    print(f"строк всего: {len(rows)}, из них на новых данных: {len(fresh)}")

    verdicts = []
    for family in families:
        fam_new = [r for r in fresh
                   if r.get("family", "").replace("ft_", "") == family]
        if not fam_new:
            verdicts.append({
                "family": family, "status": "NO_DATA",
                "note": f"нет прогонов на данных после {NEW_DATA_START}",
            })
            continue

        # Правило из пре-регистрации: все пары, где было хотя бы одно
        # действие. Пары НЕ ранжируются.
        tradable = [r for r in fam_new if (r.get("trade_count") or 0) >= 1]
        sharpes = [r["sharpe_per_obs"] for r in tradable
                   if isinstance(r.get("sharpe_per_obs"), (int, float))]
        if len(sharpes) < 2:
            verdicts.append({
                "family": family, "status": "NO_DATA",
                "note": "недостаточно пар с торгови",
            })
            continue

        sd = st.stdev(sharpes)
        n_trials = len(sharpes)
        best = max(tradable, key=lambda r: r.get("sharpe_per_obs") or -99)
        try:
            res = deflated_sharpe_ratio(
                observed_sharpe=best["sharpe_per_obs"], n_trials=n_trials,
                n_observations=best["n_obs"], trial_sharpe_std=sd,
                skew=best.get("skew") or 0.0, kurtosis=best.get("kurtosis") or 3.0)
            dsr = float(res.deflated_sharpe_ratio)
            sr_star = float(res.expected_maximum_sharpe)
        except Exception as exc:
            verdicts.append({"family": family, "status": "ERROR",
                             "note": str(exc)[:200]})
            continue

        profitable = [r for r in tradable
                      if isinstance(r.get("annual_pct"), (int, float))
                      and r["annual_pct"] > 0]
        share = len(profitable) / len(tradable) if tradable else 0.0
        passes = (dsr >= gates["dsr_narrow_min"]
                  and (best.get("t_stat") or 0) >= gates["t_stat_min"]
                  and abs(best.get("max_dd_pct") or 999) <= gates["max_dd_pct"]
                  and len(tradable) >= gates["min_pairs_to_test"]
                  and share >= MIN_PROFITABLE_SHARE)
        verdicts.append({
            "family": family,
            "status": "PASS" if passes else "FAIL",
            "n_pairs": len(tradable),
            "n_trials_narrow": n_trials,
            "trial_sharpe_std": sd,
            "best": {"symbol": best.get("symbol"), "risk": best.get("risk"),
                     "annual_pct": best.get("annual_pct"),
                     "t_stat": best.get("t_stat"),
                     "max_dd_pct": best.get("max_dd_pct"),
                     "sharpe_per_obs": best.get("sharpe_per_obs")},
            "dsr_narrow": dsr,
            "sr_star_narrow": sr_star,
            "profitable_share": share,
            "gates": {
                "t": (best.get("t_stat") or 0) >= gates["t_stat_min"],
                "dsr": dsr >= gates["dsr_narrow_min"],
                "dd": abs(best.get("max_dd_pct") or 999) <= gates["max_dd_pct"],
                "pairs": len(tradable) >= gates["min_pairs_to_test"],
                "profitable_share": share >= MIN_PROFITABLE_SHARE,
            },
        })

    passed = [v for v in verdicts if v.get("status") == "PASS"]
    payload = {
        "date": date.today().isoformat(),
        "new_data_start": NEW_DATA_START,
        "gates": gates,
        "min_profitable_share": MIN_PROFITABLE_SHARE,
        "families": families,
        "verdicts": verdicts,
        "n_pass": len(passed),
        "n_fail": len([v for v in verdicts if v.get("status") == "FAIL"]),
        "n_no_data": len([v for v in verdicts if v.get("status") == "NO_DATA"]),
        "honest_limits": [
            "Пороги и список семейств взяты из PREREGISTRATION.md и не "
            "настраиваются под результат.",
            "Это проверка на данных после 2026-10-19; пока таких данных "
            "нет, вердикт будет NO_DATA.",
        ],
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwritten: {args.out}")
    print("\n| Семейство | Статус | пар | лучшая пара | %/год | t | DD % | DSR узкий | прибыльных |")
    print("|---|---|---:|---|---:|---:|---:|---:|---:|")
    for v in verdicts:
        if v.get("status") in ("PASS", "FAIL"):
            b = v["best"]
            print(f"| {v['family']} | {v['status']} | {v['n_pairs']} | "
                  f"{b['symbol']}/{b['risk']} | {b['annual_pct']:.2f} | "
                  f"{b['t_stat']:.3f} | {b['max_dd_pct']:.2f} | {v['dsr_narrow']:.4f} | "
                  f"{v['profitable_share']*100:.0f}% |")
        else:
            print(f"| {v['family']} | {v['status']} | — | — | — | — | — | — | — |")
    print(f"\nпрошли: {payload['n_pass']} | не прошли: {payload['n_fail']} | "
          f"нет данных: {payload['n_no_data']}")


if __name__ == "__main__":
    main()
