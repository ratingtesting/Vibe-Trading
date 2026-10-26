"""Walk-forward проверка: отбор на первых годах, проверка на последних.

Зачем: гейт DSR >= 0.95 при пуле 42 299 недостижим арифметически - это не
значит, что края нет, это значит, что гейт не отвечает на вопрос. Честный
способ ответить - не сузить пул ПОСЛЕ ФАКТА (это тот же оверфит, только
замаскированный), а проверить устойчивость на ВРЕМЕНИ:

    1. Для каждого из 34 980 прогонов считаем метрики на первых 3 годах
       (train: 2021-10-20 .. 2024-10-19) и на последних 2 годах
       (test: 2024-10-20 .. 2026-10-19).
    2. Отбираем кандидатов ПО ТОЛЬКО НА TRAIN (по Sharpe).
    3. Смотрим, что с ними на TEST - и считаем DSR на TEST по ПОЛНОМУ пулу,
       то есть по всем 34 980 строкам, посчитанным на том же test-периоде.

Почему это честно, а не самообман: если край реален, стратегия должна
показать положительный Sharpe на обоих периодах. Если она выиграла только
на train - это была удача, а не край, и test-проверка это покажет.

Всё считается из сырых дневных доходностей (.npz), по той же формуле, что
и основной скан: годовая доходность (prod(1+r))^(365/n)-1, Sharpe на
наблюдение mean/std, DSR через боевую функцию проекта.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
SCAN = FOUNDER / "scan5y"
RETURNS = SCAN / "returns"
RESULTS = SCAN / "scan-results.jsonl"
OUT = SCAN / "walk-forward.json"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(FOUNDER))

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

ANNUALISATION = 365.0
# 1826 баров на 5 лет. 3 года = 1096 баров, 2 года = 730 баров.
TRAIN_BARS = 1096
TEST_BARS = 730

# Мёртвые токены: цена упала в ноль, торговать их нельзя.
DEAD_SYMBOLS = {"LUNAUSDT"}


def _metrics(ret: np.ndarray) -> dict[str, Any]:
    """Метрики среза по той же формуле, что и в scan5y."""
    n = ret.size
    if n < 30:
        return {"annual_pct": None, "sharpe_per_obs": None, "t_stat": None,
                "max_dd_pct": None, "n_obs": n}
    sd = float(np.std(ret, ddof=1))
    sharpe = float(np.mean(ret)) / sd if sd > 0 else None
    t_stat = float(np.mean(ret) / sd * math.sqrt(n)) if sd > 0 else None
    equity = np.cumprod(1.0 + ret)
    dd = float((equity / np.maximum.accumulate(equity) - 1.0).min()) * 100.0
    annual = float((1.0 + ret).prod() ** (ANNUALISATION / n) - 1.0) * 100.0
    if not math.isfinite(annual):
        annual = None
    return {"annual_pct": annual, "sharpe_per_obs": sharpe, "t_stat": t_stat,
            "max_dd_pct": abs(dd), "n_obs": n}


def _one(path_str: str) -> dict[str, Any] | None:
    """Метрики train/test для одного прогона."""
    path = Path(path_str)
    try:
        with np.load(path) as data:
            ret = np.asarray(data["ret"], dtype=float)
    except (OSError, ValueError, KeyError):
        return None
    if ret.size < TRAIN_BARS + TEST_BARS:
        return None
    train = ret[:TRAIN_BARS]
    test = ret[-TEST_BARS:]
    return {"idx": int(path.stem), "train": _metrics(train), "test": _metrics(test)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    rows = [json.loads(line) for line in RESULTS.open(encoding="utf-8") if line.strip()]
    meta = {}
    for row in rows:
        if row.get("status") == "OK":
            meta[int(row["idx"])] = row

    files = sorted(str(p) for p in RETURNS.glob("*.npz"))
    print(f"файлов доходностей: {len(files)}")

    metrics: dict[int, dict] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, item in enumerate(pool.map(_one, files, chunksize=64), start=1):
            if item is not None:
                metrics[item["idx"]] = item
            if i % 5000 == 0:
                print(f"  {i}/{len(files)}", flush=True)

    print(f"разобрано: {len(metrics)}")

    # Полный пул: DSR считается по ВСЕМ строкам, что были прогнаны.
    train_sharpes = [m["train"]["sharpe_per_obs"] for m in metrics.values()
                     if m["train"]["sharpe_per_obs"] is not None]
    test_sharpes = [m["test"]["sharpe_per_obs"] for m in metrics.values()
                    if m["test"]["sharpe_per_obs"] is not None]
    train_std = st.stdev(train_sharpes) if len(train_sharpes) > 1 else 0.0
    test_std = st.stdev(test_sharpes) if len(test_sharpes) > 1 else 0.0

    for m in metrics.values():
        for part, std in (("train", train_std), ("test", test_std)):
            row = m[part]
            sharpe = row["sharpe_per_obs"]
            if sharpe is None:
                row["dsr"] = None
                continue
            src = meta.get(m["idx"], {})
            try:
                res = deflated_sharpe_ratio(
                    observed_sharpe=sharpe, n_trials=len(metrics),
                    n_observations=row["n_obs"], trial_sharpe_std=std,
                    skew=src.get("skew") or 0.0, kurtosis=src.get("kurtosis") or 3.0)
                row["dsr"] = float(res.deflated_sharpe_ratio)
                row["expected_max_sharpe"] = float(res.expected_maximum_sharpe)
            except (ValueError, ZeroDivisionError, TypeError):
                row["dsr"] = None

    # Отбор: ТОЛЬКО по train. Test не участвует в выборе.
    tradable = [m for m in metrics.values()
                if meta.get(m["idx"], {}).get("symbol") not in DEAD_SYMBOLS]
    selected = sorted(
        [m for m in tradable
         if m["train"]["sharpe_per_obs"] is not None
         and m["train"]["sharpe_per_obs"] > 0],
        key=lambda m: -m["train"]["sharpe_per_obs"])[:args.top]

    def describe(m: dict) -> dict[str, Any]:
        src = meta.get(m["idx"], {})
        return {
            "idx": m["idx"],
            "family": src.get("family"), "symbol": src.get("symbol"),
            "risk": src.get("risk"),
            "params": src.get("params"),
            "train": m["train"], "test": m["test"],
        }

    # Итог: сколько из отобранных на train остаются прибыльными на test.
    positive_test = [m for m in selected
                     if (m["test"]["sharpe_per_obs"] or -99) > 0]
    survivors = [m for m in selected
                 if (m["test"]["dsr"] is not None and m["test"]["dsr"] >= 0.95
                     and (m["test"]["t_stat"] or 0) >= 2.5
                     and (m["test"]["max_dd_pct"] or 999) <= 20.0)]

    payload = {
        "date": "2026-10-26",
        "method": ("отбор по train (первые 3 года), проверка по test "
                   "(последние 2 года); DSR на test считается по ПОЛНОМУ пулу"),
        "train_period": "2021-10-20 .. 2024-10-19 (1096 баров)",
        "test_period": "2024-10-20 .. 2026-10-19 (730 баров)",
        "pool_size": len(metrics),
        "n_train_pool": len(train_sharpes),
        "n_test_pool": len(test_sharpes),
        "train_sharpe_std": train_std,
        "test_sharpe_std": test_std,
        "n_selected_by_train": len(selected),
        "n_positive_on_test": len(positive_test),
        "n_survivors_dsr95_t25_dd20_on_test": len(survivors),
        "selected": [describe(m) for m in selected],
        "survivors": [describe(m) for m in survivors],
        "honest_limits": [
            "Отбор сделан только по train; test не участвовал в выборе.",
            "DSR на test посчитан по полному пулу - как и положено.",
            "Мёртвый токен LUNAUSDT исключён.",
            "Это проверка устойчивости, а не новый независимый тест: "
            "те же данные, что уже смотрели.",
        ],
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding="utf-8")

    # Полные метрики сохраняем компактно - без них нельзя ответить на главный
    # вопрос: работает ли отбор на train вообще (для этого нужны t_stat и
    # Sharpe ВСЕХ строк, а не только отобранных 40).
    dump = OUT.with_name("walk-forward-metrics.npz")
    np.savez_compressed(
        dump,
        idx=np.array([m["idx"] for m in metrics.values()], dtype=np.int32),
        train_sharpe=np.array([m["train"]["sharpe_per_obs"] if m["train"]["sharpe_per_obs"] is not None else np.nan for m in metrics.values()], dtype=np.float32),
        train_t=np.array([m["train"]["t_stat"] if m["train"]["t_stat"] is not None else np.nan for m in metrics.values()], dtype=np.float32),
        train_dd=np.array([m["train"]["max_dd_pct"] if m["train"]["max_dd_pct"] is not None else np.nan for m in metrics.values()], dtype=np.float32),
        test_sharpe=np.array([m["test"]["sharpe_per_obs"] if m["test"]["sharpe_per_obs"] is not None else np.nan for m in metrics.values()], dtype=np.float32),
        test_t=np.array([m["test"]["t_stat"] if m["test"]["t_stat"] is not None else np.nan for m in metrics.values()], dtype=np.float32),
        test_dd=np.array([m["test"]["max_dd_pct"] if m["test"]["max_dd_pct"] is not None else np.nan for m in metrics.values()], dtype=np.float32),
        test_annual=np.array([m["test"]["annual_pct"] if m["test"]["annual_pct"] is not None else np.nan for m in metrics.values()], dtype=np.float32),
    )
    print(f"\nwritten: {dump}")

    print("\n| # | Стратегия | Пара | Риск | train %/год | train t | test %/год | test t | test DSR | test DD % | test Sharpe |")
    print("|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for i, m in enumerate(selected[:25], start=1):
        src = meta.get(m["idx"], {})
        tr, te = m["train"], m["test"]
        print(f"| {i} | {src.get('family')} | {src.get('symbol')} | {src.get('risk')} | "
              f"{tr['annual_pct'] if tr['annual_pct'] is not None else 0:.2f} | "
              f"{tr['t_stat'] if tr['t_stat'] is not None else 0:.3f} | "
              f"{te['annual_pct'] if te['annual_pct'] is not None else 0:.2f} | "
              f"{te['t_stat'] if te['t_stat'] is not None else 0:.3f} | "
              f"{te['dsr'] if te['dsr'] is not None else 0:.4f} | "
              f"{te['max_dd_pct'] if te['max_dd_pct'] is not None else 0:.2f} | "
              f"{te['sharpe_per_obs'] if te['sharpe_per_obs'] is not None else 0:.5f} |")

    print(f"\nотобрано на train: {len(selected)}")
    print(f"из них прибыльны на test: {len(positive_test)} "
          f"({len(positive_test)*100//max(len(selected),1)}%)")
    print(f"прошли гейт на test (DSR>=0.95, t>=2.5, DD<=20%): {len(survivors)}")


if __name__ == "__main__":
    main()
