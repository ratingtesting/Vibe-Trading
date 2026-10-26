"""Честный пересчёт DSR по ВСЕМ прогонам: старые блоки + новый 5-летний скан.

ЗАЧЕМ ЭТОТ ФАЙЛ (вместо прежнего honest_dsr_recheck.py)
Старые прогоны ужаты в компактный след (npz с дневной доходностью), а новый
5-летний скан держит свой формат. Этот модуль читает ОБА источника через
run_returns.py, поэтому пересчёт работает и до, и после упаковки.

ЧТО СЧИТАЕТСЯ (правила зафиксированы в research_metrics.py)
1. Наблюдаемый Sharpe — ПОПЕРИОДНЫЙ (mean/std), как требует
   src/quantlib/multipletesting.py. Годовой Sharpe завышает DSR примерно
   в sqrt(365) раз — именно из-за этого прежние «PASS» не выдержали
   проверки.
2. Дисперсия пула — стандартное отклонение (ddof=1) периодных Sharpe по
   ВСЕМ строкам, в той же шкале. Не дисперсия: без корня порог падает
   примерно в 50 раз и DSR показывает 0.9997 вместо 0.42.
3. skew/kurtosis — по реальному ряду доходности, kurtosis НЕэксцессовая.
4. Просадка в артефактах отрицательная: «не хуже 20%» это |dd| <= 20.
5. Отсутствующее значение — None, а не ноль: неизвестный результат гейт
   не проходит.

ГЕЙТЫ (канон владельца)
   ЭТАЛОН   = t>=3   + DSR>=0.95 + |DD|<=20%
   КАНДИДАТ = t>=2.5 + DSR>=0.95 + |DD|<=20%
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"

sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(FOUNDER))
sys.path.insert(0, str(FOUNDER / "archetypes"))

import run_returns as rr  # noqa: E402
from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

OUT = FOUNDER / "honest-dsr-final.json"
MIN_OBS = 30


def _metrics(ret: np.ndarray) -> dict[str, Any]:
    """Метрики строки в согласованной шкале."""
    if ret.size < MIN_OBS:
        return {"n_obs": int(ret.size), "sharpe_per_obs": None, "t_stat": None,
                "skew": None, "kurtosis": None, "max_dd_pct": None}
    values = ret.astype(float)
    std = float(values.std(ddof=1))
    if std <= 0:
        return {"n_obs": int(values.size), "sharpe_per_obs": None, "t_stat": None,
                "skew": None, "kurtosis": None, "max_dd_pct": None}
    sharpe = float(values.mean() / std)
    t_stat = float(values.mean() / std * math.sqrt(values.size))
    centred = (values - values.mean()) / std
    skew = float(np.mean(centred**3))
    kurtosis = float(np.mean(centred**4))
    equity = np.cumprod(1.0 + values)
    dd = float((equity / np.maximum.accumulate(equity) - 1.0).min())
    return {"n_obs": int(values.size), "sharpe_per_obs": sharpe, "t_stat": t_stat,
            "skew": skew, "kurtosis": kurtosis, "max_dd_pct": abs(dd) * 100.0}


def collect() -> list[dict[str, Any]]:
    """Все строки: старые блоки (упаковка) + новый 5-летний скан."""
    rows: list[dict[str, Any]] = []

    # --- старые блоки: из упаковки (приоритет) или из equity.csv ----------
    old_metrics = rr.load_old_metrics()
    for (block, name), meta in old_metrics.items():
        packed = rr.load_old_return(block, name)
        ret = None
        if packed is not None:
            ret = packed[0]
        else:
            path = FOUNDER / block / name / "artifacts" / "equity.csv"
            if path.exists():
                frame = pd.read_csv(path, parse_dates=["timestamp"])
                frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
                ret = frame["ret"].dropna().astype(float).to_numpy()
        if ret is None:
            continue
        m = _metrics(ret)
        if m["sharpe_per_obs"] is None:
            continue
        rows.append({"source": "старые-блоки", "block": block, "name": name,
                     "family": "", "risk": "", "symbol": "", **m})

    # --- новый 5-летний скан --------------------------------------------
    for row in rr.load_new_rows():
        if row.get("status") != "OK":
            continue
        ret = rr.load_new_return(int(row["idx"]))
        if ret is None:
            continue
        m = _metrics(ret)
        if m["sharpe_per_obs"] is None:
            continue
        rows.append({"source": "скан-5лет", "block": "scan5y",
                     "name": f"{row['family']}/{row['symbol']}/{row['risk']}",
                     "family": row["family"], "risk": row["risk"],
                     "symbol": row["symbol"], **m})

    return rows


def main() -> None:
    rows = collect()
    if not rows:
        raise SystemExit("нет ни одной строки для пересчёта")

    sharpes = [r["sharpe_per_obs"] for r in rows]
    n_trials = len(rows)
    # ВАЖНО: стандартное отклонение (ddof=1), а не дисперсия. Без корня
    # порог максимального Sharpe падает примерно в 50 раз, и DSR показывает
    # 0.9997 вместо честного 0.42 (регрессия в test_dsr_pool_dispersion.py).
    trial_std = float(pd.Series(sharpes).std(ddof=1))
    expected_fp = n_trials * 0.05

    print(f"строк в пуле: {n_trials}")
    print(f"разброс Sharpe по пулу (попериодный): {trial_std:.6f}")
    print(f"ожидаемые ложные срабатывания при 5%: {expected_fp:.1f}")

    for r in rows:
        try:
            res = deflated_sharpe_ratio(
                observed_sharpe=r["sharpe_per_obs"], n_trials=n_trials,
                n_observations=r["n_obs"], trial_sharpe_std=trial_std,
                skew=r["skew"], kurtosis=r["kurtosis"])
            r["dsr"] = float(res.deflated_sharpe_ratio)
        except (ValueError, ZeroDivisionError, TypeError):
            r["dsr"] = None
        t = r["t_stat"]
        dd = r["max_dd_pct"]
        r["gate_reference"] = bool(
            t is not None and t >= 3.0 and (r["dsr"] or 0) >= 0.95
            and dd is not None and dd <= 20.0)
        r["gate_candidate"] = bool(
            t is not None and t >= 2.5 and (r["dsr"] or 0) >= 0.95
            and dd is not None and dd <= 20.0)

    reference = sorted([r for r in rows if r["gate_reference"]],
                        key=lambda r: -(r["sharpe_per_obs"] or 0))
    candidates = sorted([r for r in rows if r["gate_candidate"]],
                         key=lambda r: -(r["sharpe_per_obs"] or 0))
    by_dsr = sorted(rows, key=lambda r: -(r["dsr"] or 0))

    verdict = {
        "date": "2026-10-25",
        "scale": "per-observation Sharpe (mean/std) без sqrt(365)",
        "n_trials_pooled": n_trials,
        "trial_sharpe_std": trial_std,
        "expected_false_positives_5pct": round(expected_fp, 1),
        "n_old_rows": len([r for r in rows if r["source"] == "старые-блоки"]),
        "n_new_rows": len([r for r in rows if r["source"] == "скан-5лет"]),
        "n_reference": len(reference),
        "n_candidate": len(candidates),
        "reference_edges": reference[:100],
        "candidates_top100": candidates[:100],
        "top_by_dsr": by_dsr[:100],
        "all_rows": rows,
        "limitation": "DSR предполагает независимость испытаний; стратегии на одной паре коррелированы. "
                     "skew/kurtosis — по реальному ряду, kurtosis неэксцессовая. "
                     "Это пересчёт уже просмотренных данных, а не новый чистый тест.",
    }
    OUT.write_text(json.dumps(verdict, indent=1, ensure_ascii=False, default=str),
                   encoding="utf-8")

    print(f"\n=== ЧЕСТНЫЙ DSR-ПЕРЕСЧЁТ ПО ВСЕМУ ПУЛУ ===")
    print(f"ЭТАЛОН (t>=3 + DSR>=0.95 + |DD|<=20%): {len(reference)}")
    for r in reference[:20]:
        print(f"  {r['source']:12s} {r['name'][:34]:34s} t={r['t_stat']:.3f} "
              f"DSR={r['dsr']:.4f} DD={r['max_dd_pct']:.1f}%")
    print(f"КАНДИДАТ (t>=2.5 + DSR>=0.95 + |DD|<=20%): {len(candidates)}")
    for r in candidates[:20]:
        print(f"  {r['source']:12s} {r['name'][:34]:34s} t={r['t_stat']:.3f} "
              f"DSR={r['dsr']:.4f} DD={r['max_dd_pct']:.1f}%")
    print(f"\nстарых строк: {verdict['n_old_rows']} | новых (5 лет): {verdict['n_new_rows']}")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
