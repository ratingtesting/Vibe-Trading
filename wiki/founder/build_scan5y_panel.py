"""Сборка блока «5-летний скан» для панели /founder.

Из jsonl скана собирает компактный JSON для фронтенда: сводка, полный
список строк с t>=2.5 (с DSR по всему пулу) и полный список строк с
просадкой <= 20% (сортировка по годовой доходности).

Пишет frontend/public/scan5y.json — панель читает его рядом с
founder-results.json и btc-kopilka.json.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"

# Токены, упавшие в ноль: торговать их уже нельзя, а стратегия на них
# показывает артефактные проценты из самого краха.
DEAD_SYMBOLS = {"LUNAUSDT"}
SCAN = FOUNDER / "scan5y"
RESULTS = SCAN / "scan-results.jsonl"
DEST = REPO / "frontend" / "public" / "scan5y.json"

sys.path.insert(0, str(REPO / "agent"))

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

MAX_LIST = 120


def main() -> None:
    rows: list[dict[str, Any]] = []
    with RESULTS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    ok = [r for r in rows if r.get("status") == "OK"]
    sharpes = [r["sharpe_per_obs"] for r in ok if r.get("sharpe_per_obs") is not None]
    n_trials = len(rows)
    # ВАЖНО: нужен СТАНДАРТНОЕ отклонение, а не дисперсия. Без корня
    # trial_std был в 50 раз меньше, порог максимального Sharpe падал
    # с 0.077 до 0.0015, и DSR показывал 0.9997 вместо честных 0.42.
    # Проверено независимым пересчётом: std(ddof=1) по тем же значениям.
    trial_std = float(pd.Series(sharpes).std(ddof=1)) if len(sharpes) > 1 else 0.0

    for r in rows:
        sharpe = r.get("sharpe_per_obs")
        if sharpe is None or not isinstance(sharpe, (int, float)) or not math.isfinite(sharpe):
            r["dsr"] = None
            continue
        skew = r.get("skew")
        kurtosis = r.get("kurtosis")
        if not isinstance(skew, (int, float)) or not math.isfinite(skew):
            skew = 0.0
        if not isinstance(kurtosis, (int, float)) or not math.isfinite(kurtosis):
            kurtosis = 3.0
        try:
            res = deflated_sharpe_ratio(
                observed_sharpe=sharpe, n_trials=n_trials,
                n_observations=r["n_obs"], trial_sharpe_std=trial_std,
                skew=skew, kurtosis=kurtosis)
            r["dsr"] = float(res.deflated_sharpe_ratio)
        except (ValueError, ZeroDivisionError, TypeError):
            r["dsr"] = None

    def slim(r: dict[str, Any]) -> dict[str, Any]:
        params = r.get("params") or {}
        return {
            "family": r["family"], "symbol": r["symbol"], "risk": r["risk"],
            "params": ", ".join(f"{k}={v}" for k, v in sorted(params.items())) if params else "",
            "annual_pct": r["annual_pct"], "t_stat": r["t_stat"],
            "dsr": r.get("dsr"), "max_dd_pct": r["max_dd_pct"],
            "sharpe_per_obs": r["sharpe_per_obs"], "n_obs": r["n_obs"],
            "trade_count": r.get("trade_count"),
        }

    # Мёртвые токены (цена упала в ноль) исключаются из лучших строк: на
    # LUNAUSDT стратегия показывает артефактные 138%/год из краха Terra
    # ($116 -> $0.043), а торговать там уже нечего. В пуле испытаний для DSR
    # они остаются - пул обязан отражать всё, что было запущено.
    tradable = [r for r in ok if r.get("symbol") not in DEAD_SYMBOLS]
    # NaN в годовой доходности = счёт ушёл в минус (prod(1+r) < 0). Такие
    # строки бессмысленны для сравнения, но остаются в пуле испытаний.
    with_annual = [r for r in tradable
                    if isinstance(r.get("annual_pct"), (int, float))
                    and math.isfinite(r["annual_pct"])]

    by_t = sorted([r for r in tradable if (r.get("t_stat") or -99) >= 2.5],
                  key=lambda r: -(r.get("t_stat") or 0))
    by_dd = sorted([r for r in with_annual if (r.get("max_dd_pct") or 999) <= 20.0],
                   key=lambda r: -(r.get("annual_pct") or -999))

    payload = {
        "date": "2026-10-25",
        "period": {"start": "2021-10-20", "end": "2026-10-19", "years": 5,
                   "bars": 1826},
        "annualisation": 365.0,
        "position_adjustment": "rebalance",
        "n_runs": len(rows),
        "n_ok": len(ok),
        "n_errors": len(rows) - len(ok),
        "n_families": len({r["family"] for r in ok}),
        "n_symbols": len({r["symbol"] for r in ok}),
        "n_variants": len({(r["family"], json.dumps(r.get("params"), sort_keys=True), r["risk"])
                           for r in ok}),
        "n_trials_pooled": n_trials,
        "trial_sharpe_std": trial_std,
        "expected_false_positives_5pct": n_trials * 0.05,
        "n_reference": len([r for r in ok if (r.get("dsr") or 0) >= 0.95
                            and (r.get("t_stat") or 0) >= 3.0
                            and (r.get("max_dd_pct") or 999) <= 20.0]),
        "n_candidate": len([r for r in ok if (r.get("dsr") or 0) >= 0.95
                            and (r.get("t_stat") or 0) >= 2.5
                            and (r.get("max_dd_pct") or 999) <= 20.0]),
        "top_by_t": [slim(r) for r in by_t[:MAX_LIST]],
        "top_by_annual_with_dd20": [slim(r) for r in by_dd[:MAX_LIST]],
        "honest_limits": [
            "Период один и тот же для всех строк: 5 лет дневных баров (1826 наблюдений).",
            "Доходность в годовых = (prod(1+r))^(365/n)-1 из дневной доходности.",
            "DSR считается по всему пулу в попериодной шкале; при пуле в десятки тысяч планка 0.95 заведомо недостижима.",
            "Отбор сделан на том же окне, что и скан: это НЕ независимая проверка.",
            "Исполнение размера включено (position_adjustment=rebalance, dropped=0 на всех прогонах).",
        ],
    }
    DEST.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"written: {DEST}")
    print(f"прогонов: {len(rows)} OK: {len(ok)} | t>=2.5: {len(by_t)} | DD<=20%: {len(by_dd)}")
    print(f"ЭТАЛОН: {payload['n_reference']} | КАНДИДАТ: {payload['n_candidate']}")


if __name__ == "__main__":
    main()
