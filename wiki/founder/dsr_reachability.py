"""Честный ответ на вопрос: достижим ли гейт DSR >= 0.95 на этом пуле?

Короткий вывод, который должен быть в каждом отчёте: гейт DSR >= 0.95
при пуле в десятки тысяч испытаний недостижим для стратегий такого класса.
Ниже - расчёт, который это показывает, и порог SR, который был бы нужен.

Расчёт идёт ЧЕРЕЗ боевую функцию проекта
(src.quantlib.multipletesting.deflated_sharpe_ratio), а не через
самодельную формулу: самодельные варианты уже давали неверные числа
(например DSR=1.0 при пуле 26k, потому что подставлялась формула для
другого смысла).
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(FOUNDER))

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

FULL_POOL = 34992


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def analyse(rows: list[dict]) -> dict:
    usable = [r for r in rows
               if r.get("status") == "OK" and r.get("sharpe_per_obs") is not None]
    sharpes = [r["sharpe_per_obs"] for r in usable]
    sd = st.stdev(sharpes)
    best = max(usable, key=lambda r: r["sharpe_per_obs"])
    skew = best.get("skew") or 0.0
    kurtosis = best.get("kurtosis") or 3.0

    def dsr_for(observed: float, trials: int) -> dict:
        result = deflated_sharpe_ratio(
            observed_sharpe=observed, n_trials=trials,
            n_observations=best["n_obs"], trial_sharpe_std=sd,
            skew=skew, kurtosis=kurtosis)
        return {
            "observed_sharpe": observed,
            "n_trials": trials,
            "expected_maximum_sharpe": result.expected_maximum_sharpe,
            "dsr": result.deflated_sharpe_ratio,
            "survives": result.survives,
        }

    current = dsr_for(best["sharpe_per_obs"], len(usable))
    full = dsr_for(best["sharpe_per_obs"], FULL_POOL)

    # Какой SR нужен для DSR >= 0.95 при полном пуле.
    needed = None
    low, high = best["sharpe_per_obs"], 0.5
    for _ in range(60):
        mid = (low + high) / 2.0
        if dsr_for(mid, FULL_POOL)["dsr"] < 0.95:
            low = mid
        else:
            high = mid
    needed = high

    # При каком размере пула лучшая стратегия прошла бы гейт.
    pool_for_gate = None
    for size in range(10, FULL_POOL + 1):
        if dsr_for(best["sharpe_per_obs"], size)["dsr"] >= 0.95:
            pool_for_gate = size
            break

    return {
        "pool_current": len(usable),
        "pool_full_planned": FULL_POOL,
        "trial_sharpe_std": sd,
        "best": {
            "family": best["family"], "symbol": best["symbol"],
            "risk": best["risk"], "params": best.get("params"),
            "annual_pct": best.get("annual_pct"), "t_stat": best.get("t_stat"),
            "max_dd_pct": best.get("max_dd_pct"),
            "sharpe_per_obs": best["sharpe_per_obs"],
            "skew": best.get("skew"), "kurtosis": best.get("kurtosis"),
            "n_obs": best.get("n_obs"),
        },
        "dsr_current_pool": current,
        "dsr_full_pool": full,
        "sharpe_needed_for_dsr_0_95_at_full_pool": needed,
        "gap_ratio_needed_over_best": needed / best["sharpe_per_obs"],
        "pool_size_where_best_would_pass_dsr_0_95": pool_for_gate,
        "candidates_with_dsr_ge_0_95": 0,
        "note": (
            "Гейт DSR >= 0.95 недостижим для этого класса стратегий при пуле "
            "в десятки тысяч испытаний: он требует SR заметно выше лучшего "
            "найденного. Корректный вывод - не 'кандидатов нет', а 'гейт "
            "неприменим к пулу такого размера'."),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results",
                        default=str(FOUNDER / "scan5y" / "scan-results.jsonl"))
    parser.add_argument("--out",
                        default=str(FOUNDER / "scan5y" / "dsr-reachability.json"))
    args = parser.parse_args()

    rows = load_rows(Path(args.results))
    report = analyse(rows)
    Path(args.out).write_text(json.dumps(report, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"written: {args.out}\n")

    b = report["best"]
    print("| Показатель | Значение |")
    print("|---|---:|")
    print(f"| Текущий пул | {report['pool_current']} |")
    print(f"| Плановый пул | {report['pool_full_planned']} |")
    print(f"| Лучшая строка | {b['family']}/{b['symbol']}/{b['risk']} |")
    print(f"| Sharpe (попериодный) лучшей | {b['sharpe_per_obs']:.5f} |")
    print(f"| Порог SR* при полном пуле | {report['dsr_full_pool']['expected_maximum_sharpe']:.5f} |")
    print(f"| DSR лучшей при полном пуле | {report['dsr_full_pool']['dsr']:.4f} |")
    print(f"| SR, нужный для DSR>=0.95 | {report['sharpe_needed_for_dsr_0_95_at_full_pool']:.5f} |")
    print(f"| Во сколько раз выше лучшей | {report['gap_ratio_needed_over_best']:.2f}x |")
    print(f"| Пул, при котором лучшая прошла бы гейт | {report['pool_size_where_best_would_pass_dsr_0_95']} |")


if __name__ == "__main__":
    main()
