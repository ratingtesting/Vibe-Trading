"""Пороговая сетка копилки на 13 кандидатах за 5 лет (данные из упаковки).

Источник: wiki/founder/old-returns/ — доходность и цена актива каждого
из 13 кандидатов. Эти данные НЕ зависят от текущего 5-летнего скана, так
что расчёт безопасен параллельно прогону.

ЧТО СЧИТАЕТСЯ
Для каждого из 13 кандидатов и сетки порогов (10/15/20/30/50% роста):
сколько раз сработало правило, сколько BTC накоплено, итоговый счёт и как
изменились годовая доходность и просадка относительно базы.

ПОЧЕМУ СЕТКА, А НЕ ОДИН ПОРОГ
При 30% (порог владельца) правило не срабатывает ни разу на
риск-контролируемых вариантах: при 8%/год до +30% не дорасти. Рычаг — порог,
поэтому его и надо померить, а не угадывать.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OUT = FOUNDER / "candidates-13-5y" / "kopilka-thresholds-13.json"

sys.path.insert(0, str(FOUNDER))

import run_returns as rr  # noqa: E402
import kopilka_5y as kop  # noqa: E402

CANDIDATES = [
    ("TSMOM-154", "archetype-scan", "SOLUSDT", "raw"),
    ("TSMOM-94", "archetype-scan", "SOLUSDT", "raw"),
    ("RegimeSwitching-864", "archetype-scan", "ZILUSDT", "raw"),
    ("RegimeSwitching-935", "archetype-scan", "ADAUSDT", "raw"),
    ("MARegimeFilter-214", "archetype-scan", "SOLUSDT", "raw"),
    ("RegimeSwitching-905", "archetype-scan", "ADAUSDT", "raw"),
    ("RegimeSwitching-875", "archetype-scan", "ADAUSDT", "raw"),
    ("TSMOM-4", "archetype-scan", "SOLUSDT", "raw"),
    ("TSMOM-SOLUSDT-ddthrottle-16", "risk-overlay", "SOLUSDT", "ddthrottle"),
    ("RegimeSwitching-993", "archetype-scan", "BNBUSDT", "raw"),
    ("RegimeSwitching-ADAUSDT-ddthrottle-36", "risk-overlay", "ADAUSDT", "ddthrottle"),
    ("RegimeSwitching-ADAUSDT-ddthrottle-40", "risk-overlay", "ADAUSDT", "ddthrottle"),
    ("RegimeSwitching-ADAUSDT-ddthrottle-28", "risk-overlay", "ADAUSDT", "ddthrottle"),
]

THRESHOLDS = (0.10, 0.15, 0.20, 0.30, 0.50)
SHARES = (0.50, 0.75)
RETURN_SHARES = (0.00, 0.30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    btc = kop._btc_close()
    rows: list[dict[str, Any]] = []

    for cid, block, symbol, risk in CANDIDATES:
        packed = rr.load_old_return(block, cid)
        if packed is None:
            print(f"  {cid}: нет данных в упаковке — пропущен")
            continue
        ret, close = packed
        if close is None:
            print(f"  {cid}: нет цены актива — пропущен")
            continue
        ret = ret.astype(float)
        n = ret.size
        asset = kop._load_close(symbol)
        if len(asset) < n:
            print(f"  {cid}: недостаточно баров — пропущен")
            continue
        dates = asset.index[-n:]
        equity = (1.0 + ret).cumprod() * kop.START_CAPITAL
        strategy = pd.Series(equity, index=dates)
        asset_aligned = pd.Series(close, index=dates)
        base_annual = float((1.0 + ret).prod() ** (365.0 / n) - 1.0) * 100.0
        base_eq = np.cumprod(1.0 + ret)
        base_dd = float((base_eq / np.maximum.accumulate(base_eq) - 1.0).min()) * 100.0

        variants: list[dict[str, Any]] = []
        for threshold in THRESHOLDS:
            for share in SHARES:
                for ret_share in RETURN_SHARES:
                    result = kop.run_kopilka(
                        strategy, asset_aligned, btc,
                        lock_threshold=threshold, lock_share=share,
                        return_share=ret_share)
                    if result.get("status") != "OK":
                        continue
                    variants.append({
                        "lock_threshold": threshold, "lock_share": share,
                        "return_share": ret_share,
                        "locks": result["locks"],
                        "returns_to_asset": result["returns_to_asset"],
                        "annual_pct": result["annual_pct"],
                        "max_dd_pct": result["max_dd_pct"],
                        "final_value": result["final_value"],
                        "final_btc_units": result["final_btc_units"],
                        "final_btc_value": result["final_btc_value"],
                        "final_asset_value": result["final_asset_value"],
                        "final_cash": result["final_cash"],
                        "btc_share_pct": result["btc_share_pct"],
                        "delta_annual_pct": result["annual_pct"] - base_annual,
                        "delta_dd_pct": result["max_dd_pct"] - base_dd,
                    })
        rows.append({
            "id": cid, "symbol": symbol, "risk": risk,
            "base": {"annual_pct": base_annual, "max_dd_pct": base_dd, "n_obs": n},
            "variants": variants,
        })

    payload = {
        "date": "2026-10-25",
        "source": "wiki/founder/old-returns (упакованные старые прогоны)",
        "n_candidates": len(rows),
        "thresholds": list(THRESHOLDS),
        "shares": list(SHARES),
        "return_shares": list(RETURN_SHARES),
        "honest_limits": [
            "Сравнение всегда с базой той же строки.",
            "Наложение — к реализованной дневной доходности стратегии.",
            "Правило причинное: дно по прошлым барам.",
        ],
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str),
                              encoding="utf-8")
    print(f"written: {args.out}")

    # Сводная таблица по порогам (доля 75%, возврат 30% - базовые настройки владельца).
    print("\n| Порог роста | Строк с фиксацией | Среднее фиксаций | Средняя Δ годовой | Доля улучшений |")
    print("|---|---|---|---|---|")
    for threshold in THRESHOLDS:
        fired, deltas = [], []
        for entry in rows:
            for v in entry["variants"]:
                if v["lock_threshold"] != threshold or v["lock_share"] != 0.75 or v["return_share"] != 0.30:
                    continue
                if v["locks"] > 0:
                    fired.append(v["locks"])
                    deltas.append(v["delta_annual_pct"])
        mean_locks = (sum(fired) / len(fired)) if fired else 0.0
        mean_delta = (sum(deltas) / len(deltas)) if deltas else 0.0
        improved = (len([d for d in deltas if d > 0]) / len(deltas) * 100) if deltas else 0.0
        print(f"| {threshold:.0%} | {len(fired)} | {mean_locks:.1f} | {mean_delta:+.2f} п.п. | {improved:.0f}% |")

    # Лучшие случаи.
    best: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for entry in rows:
        for v in entry["variants"]:
            if v["locks"] > 0 and v["delta_annual_pct"] > 0:
                best.append((v["delta_annual_pct"], entry, v))
    best.sort(key=lambda x: -x[0])
    if best:
        print("\n| ID | Пара | Риск | Порог | Доля | База %/год | С копилкой %/год | Δ | BTC шт | BTC $ | Актив $ | Всего $ | Доля BTC % |")
        print("|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for dv, entry, v in best[:12]:
            print(f"| {entry['id']} | {entry['symbol']} | {entry['risk']} | {v['lock_threshold']:.0%} | "
                  f"{v['lock_share']:.0%} | {entry['base']['annual_pct']:.2f} | {v['annual_pct']:.2f} | "
                  f"{dv:+.2f} | {v['final_btc_units']:.6f} | {v['final_btc_value']:.2f} | "
                  f"{v['final_asset_value']:.2f} | {v['final_value']:.2f} | {v['btc_share_pct']:.1f} |")


if __name__ == "__main__":
    main()
