"""Работает ли отбор на train? Статистика переноса train -> test.

Это главный вопрос walk-forward. Ответ может быть "нет": если взять самые
красивые строки по train и они не лучше случайных на test, то отбор по
статистике не работает вообще, и никакой гейт это не спасёт.

Считаем:
  1. Средний test-Sharpe у отобранных на train ТОП-N (для N от 10 до 2000).
  2. Тот же показатель для СЛУЧАЙНЫХ строк того же размера - это базовая
     линия, с которой сравниваем.
  3. Доля строк, у которых test-Sharpe > 0 (прибыльность на test).
  4. Корреляцию train-Sharpe с test-Sharpe по всему пулу.

Если корреляция около нуля, отбор по train не переносится: искать края по
статистике на этом пуле бессмысленно.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
METRICS = FOUNDER / "scan5y" / "walk-forward-metrics.npz"
RESULTS = FOUNDER / "scan5y" / "scan-results.jsonl"
OUT = FOUNDER / "scan5y" / "walk-forward-transfer.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default=str(METRICS))
    parser.add_argument("--out", default=str(OUT))
    parser.add_argument("--seed", type=int, default=20261026)
    args = parser.parse_args()

    with np.load(args.metrics) as data:
        idx = data["idx"]
        train_sharpe = data["train_sharpe"]
        data["train_t"]
        data["train_dd"]
        test_sharpe = data["test_sharpe"]
        data["test_t"]
        data["test_dd"]
        data["test_annual"]

    rows = [json.loads(line) for line in RESULTS.open(encoding="utf-8") if line.strip()]
    meta = {int(r["idx"]): r for r in rows if r.get("status") == "OK"}
    dead = {"LUNAUSDT"}

    valid = np.isfinite(train_sharpe) & np.isfinite(test_sharpe)
    ts = train_sharpe[valid]
    vs = test_sharpe[valid]
    idx_valid = idx[valid]
    symbols = np.array([meta.get(int(i), {}).get("symbol", "") for i in idx_valid])
    alive = np.array([s not in dead for s in symbols])

    print(f"строк с обеими метриками: {valid.sum()}, из них живых: {alive.sum()}")

    corr = float(np.corrcoef(ts, vs)[0, 1])
    print(f"корреляция train-Sharpe с test-Sharpe по всему пулу: {corr:.4f}")

    # Ранговые корреляции устойчивее к выбросам.
    def spearman(a: np.ndarray, b: np.ndarray) -> float:
        ra = np.argsort(np.argsort(a)).astype(float)
        rb = np.argsort(np.argsort(b)).astype(float)
        return float(np.corrcoef(ra, rb)[0, 1])

    print(f"ранговая корреляция (Spearman): {spearman(ts, vs):.4f}")

    ts_alive, vs_alive = ts[alive], vs[alive]
    rng = np.random.default_rng(args.seed)
    pool = vs_alive.copy()
    positive_rate = float((vs_alive > 0).mean())

    sizes = (10, 25, 50, 100, 250, 500, 1000, 2000)
    selected_mean = []

    for n in sizes:
        if n > ts_alive.size:
            continue
        order = np.argsort(-ts_alive)[:n]
        sel = float(vs_alive[order].mean())
        # 200 случайных выборок того же размера - базовая линия.
        samples = []
        for _ in range(200):
            samples.append(float(rng.choice(pool, size=n, replace=False).mean()))
        rand = float(np.mean(samples))
        rand_sd = float(np.std(samples))
        selected_mean.append({"n": n, "selected_test_sharpe_mean": sel,
                              "random_test_sharpe_mean": rand,
                              "random_std": rand_sd,
                              "advantage": sel - rand,
                              "z_score": (sel - rand) / rand_sd if rand_sd > 0 else 0.0})
        print(f"  топ-{n:5d} на train: test-Sharpe среднее {sel:+.5f} | "
              f"случайные {rand:+.5f} (sd {rand_sd:.5f}) | "
              f"преимущество {sel-rand:+.5f} (z={(sel-rand)/rand_sd if rand_sd>0 else 0:.2f})")

    # Доля прибыльных на test у отобранных и у случайных.
    top200 = np.argsort(-ts_alive)[:200]
    sel_positive_rate = float((vs_alive[top200] > 0).mean())

    payload = {
        "date": "2026-10-26",
        "n_with_metrics": int(valid.sum()),
        "n_alive": int(alive.sum()),
        "pearson_corr_train_test_sharpe": corr,
        "spearman_corr_train_test_sharpe": spearman(ts_alive, vs_alive),
        "base_positive_rate_on_test": positive_rate,
        "top200_positive_rate_on_test": sel_positive_rate,
        "transfer_table": selected_mean,
        "honest_limits": [
            "Отбор делался по train; test не участвовал в выборе.",
            "Базовая линия - 200 случайных выборок того же размера.",
            "Мёртвый токен LUNAUSDT исключён.",
            "Тот же набор данных, что уже смотрели - это проверка переноса, "
            "а не независимый тест.",
        ],
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwritten: {args.out}")
    print(f"базовая доля прибыльных на test: {positive_rate*100:.1f}%")
    print(f"у топ-200 на train: {sel_positive_rate*100:.1f}%")


if __name__ == "__main__":
    main()
