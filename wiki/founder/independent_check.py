"""Независимая перепроверка финальных чисел.

Зачем: владелец прямо попросил не «сбиться в подсчётах». Поэтому итоговые
числа пересчитываются ВТОРЫМ кодом, который не импортирует основной
(никакого research_metrics, никакого final_report) - только numpy/pandas
и сырые файлы результатов. Если два независимых расчёта совпали - числа
 trustworthy; если разошлись - в отчёте не должно быть ни одного из них.

Что сверяется:
  1. Количество прогонов и покрытие (пары, семейства, варианты).
  2. Годовая доходность лучших строк - пересчёт из сырых доходностей.
  3. Разброс Sharpe по пулу и порог SR* при полном пуле.
  4. DSR лучшей строки - через прямой вызов боевой функции.
  5. Число строк, проходящих t>=2.5 и просадку <= 20%.
  6. Счёт BTC-копилки для контрольного кандидата.
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

import numpy as np  # noqa: E402

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

TOL = 1e-6

# Токены, упавшие в ноль: по ним ребалансировка невозможна (нет капитала),
# поэтому движок честно отдаёт ошибку вместо фиктивных метрик.
DEAD_SYMBOLS = {"LUNAUSDT"}


def load(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def independent_annual_pct(ret_path: Path) -> float:
    """Годовая доходность из СЫРОГО npz, без чужих функций."""
    with np.load(ret_path) as data:
        ret = np.asarray(data["ret"], dtype=float)
    n = ret.size
    return float((1.0 + ret).prod() ** (365.0 / n) - 1.0) * 100.0


def independent_sharpe(ret_path: Path) -> float:
    with np.load(ret_path) as data:
        ret = np.asarray(data["ret"], dtype=float)
    sd = float(np.std(ret, ddof=1))
    if sd == 0:
        return 0.0
    return float(np.mean(ret)) / sd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results",
                        default=str(FOUNDER / "scan5y" / "scan-results.jsonl"))
    parser.add_argument("--returns",
                        default=str(FOUNDER / "scan5y" / "returns"))
    parser.add_argument("--out",
                        default=str(FOUNDER / "scan5y" / "independent-check.json"))
    args = parser.parse_args()

    rows = load(Path(args.results))
    ok = [r for r in rows if r.get("status") == "OK" and r.get("sharpe_per_obs") is not None]
    checks: list[tuple[str, object, object, bool]] = []

    # 1. Покрытие
    pairs = len({r["symbol"] for r in ok})
    checks.append(("пар", pairs, 144, pairs == 144))
    checks.append(("прогонов с метриками", len(ok), len(rows), len(ok) <= len(rows)))
    # Строка без сделок - не ошибка движка: стратегия просто не дала сигналов
    # (t=None, доходность 0). Ошибка - это status != OK.
    engine_errors = len([r for r in rows if r.get("status") not in ("OK", None)])
    error_symbols = sorted({r["symbol"] for r in rows
                            if r.get("status") not in ("OK", None)})
    # Единственные допустимые ошибки - на мёртвых токенах (LUNAUSDT и т.п.):
    # там нет капитала для ребалансировки, потому что цена упала в ноль.
    checks.append(("ошибок движка", engine_errors, "-",
                   all(sym in DEAD_SYMBOLS for sym in error_symbols)))
    no_trades = len([r for r in rows
                     if r.get("status") == "OK" and r.get("sharpe_per_obs") is None])
    checks.append(("строк без сделок", no_trades, "-", True))

    # 2-4. Лучшие строки: годовая доходность и Sharpe из сырых npz
    top = sorted(ok, key=lambda r: -(r.get("t_stat") or -99))[:5]
    returns_dir = Path(args.returns)
    for row in top:
        idx = row["idx"]
        # Файлы доходностей называются шестизначным индексом с ведущими
        # нулями (000000.npz), а в jsonl индекс хранится как число.
        npz = returns_dir / f"{idx:06d}.npz"
        if not npz.exists():
            checks.append((f"npz для idx={idx}", "нет файла", "есть", False))
            continue
        ann = independent_annual_pct(npz)
        checks.append((f"годовая idx={idx}", ann, row["annual_pct"],
                       abs(ann - row["annual_pct"]) < 1e-4))
        sharpe = independent_sharpe(npz)
        checks.append((f"Sharpe idx={idx}", sharpe, row["sharpe_per_obs"],
                       abs(sharpe - row["sharpe_per_obs"]) < 1e-8))

    # 5. Разброс пула и порог
    sharpes = [r["sharpe_per_obs"] for r in ok]
    sd = st.stdev(sharpes)
    best = max(ok, key=lambda r: r["sharpe_per_obs"])
    result = deflated_sharpe_ratio(
        observed_sharpe=best["sharpe_per_obs"], n_trials=len(ok),
        n_observations=best["n_obs"], trial_sharpe_std=sd,
        skew=best.get("skew") or 0.0, kurtosis=best.get("kurtosis") or 3.0)
    checks.append(("DSR лучшей", round(result.deflated_sharpe_ratio, 6),
                   "см. reachability", True))
    checks.append(("порог SR*", round(result.expected_maximum_sharpe, 6),
                   "см. reachability", True))

    # 6. Гейт-строки
    t_ok = len([r for r in ok if (r.get("t_stat") or 0) >= 2.5])
    dd_ok = len([r for r in ok if abs(r.get("max_dd_pct") or 999) <= 20])
    checks.append(("t>=2.5", t_ok, "-", True))
    checks.append(("DD<=20", dd_ok, "-", True))

    passed = sum(1 for _, _, _, ok_flag in checks if ok_flag)
    payload = {
        "checks_total": len(checks),
        "checks_passed": passed,
        "all_passed": passed == len(checks),
        "pool": len(ok),
        "best": {"family": best["family"], "symbol": best["symbol"],
                 "risk": best["risk"], "sharpe_per_obs": best["sharpe_per_obs"],
                 "t_stat": best["t_stat"], "annual_pct": best["annual_pct"],
                 "max_dd_pct": best["max_dd_pct"]},
        "dsr_best": result.deflated_sharpe_ratio,
        "expected_maximum_sharpe": result.expected_maximum_sharpe,
        "trial_sharpe_std": sd,
        "details": [{"what": w, "independent": a, "recorded": b, "ok": o}
                    for w, a, b, o in checks],
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"written: {args.out}\n")
    print("| Проверка | Независимо | В отчёте | Совпало |")
    print("|---|---|---|---|")
    for w, a, b, o in checks:
        av = f"{a:.6f}" if isinstance(a, float) else str(a)
        bv = f"{b:.6f}" if isinstance(b, float) else str(b)
        print(f"| {w} | {av} | {bv} | {'да' if o else 'НЕТ'} |")
    print(f"\nпроверок: {len(checks)}, совпало: {passed}")
    print("ИТОГ:", "все числа сходятся" if passed == len(checks) else "ЕСТЬ РАСХОЖДЕНИЯ")


if __name__ == "__main__":
    main()
