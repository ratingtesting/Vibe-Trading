"""Копилка с пониженными порогами: где правило вообще срабатывает.

НАХОДКА, КОТОРУЮ ЭТО ЧИНИТ
При пороге «+30% роста -> 75% в BTC» копилка за 5 лет сработала 6-19 раз на
агрессивных (raw) стратегиях и НИ РАЗУ на сбалансированных (vol10,
vol12dd820): при 8%/год до +30% просто не дорасти. То есть правило
работает ровно там, где оно НЕ нужно, и не работает там, где нужно.

ЧТО СЧИТАЕТСЯ
Для каждой строки-кандидата и для сетки порогов:
  lock_threshold (порог роста), lock_share (доля прироста в BTC),
  return_share (доля резерва, возвращаемая в актив)
считается: сколько раз сработало правило, сколько BTC накоплено, какой
итог, как изменилась годовая доходность и просадка.

Сравнение всегда с БАЗОЙ той же строки (без копилки).

ВЫХОД
wiki/founder/scan5y/kopilka-thresholds.json — полные таблицы
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
SCAN = FOUNDER / "scan5y"
RESULTS = SCAN / "scan-results.jsonl"
RETURNS = SCAN / "returns"
OUT = SCAN / "kopilka-thresholds.json"

sys.path.insert(0, str(FOUNDER))
sys.path.insert(0, str(FOUNDER / "archetypes"))

import kopilka_5y as kop  # noqa: E402

# Сетка порогов: владелец назвал 30-50% роста и 50-75% доли. Ниже
# добавляем 10-20%, потому что при 8%/год порог 30% недостижим.
THRESHOLDS = (0.10, 0.15, 0.20, 0.30, 0.50)
SHARES = (0.50, 0.75)
RETURN_SHARES = (0.00, 0.30)


def _load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with RESULTS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def _base_stats(returns: np.ndarray) -> dict[str, Any]:
    n = returns.size
    equity = np.cumprod(1.0 + returns)
    std = float(returns.std(ddof=1))
    return {
        "annual_pct": float((1.0 + returns).prod() ** (365.0 / n) - 1.0) * 100.0,
        "max_dd_pct": float((equity / np.maximum.accumulate(equity) - 1.0).min()) * 100.0,
        "t_stat": float(returns.mean() / std * math.sqrt(n)) if std > 0 else None,
        "n_obs": n,
    }


import math  # noqa: E402 — используется в _base_stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=25, help="сколько строк-кандидатов считать")
    args = parser.parse_args()

    rows = [r for r in _load_rows() if r.get("status") == "OK"]
    rows.sort(key=lambda r: -(r.get("t_stat") or -99))
    selected = rows[: args.top]
    print(f"кандидатов: {len(selected)}")

    btc = kop._btc_close()
    close_cache: dict[str, pd.Series] = {}
    out_rows: list[dict[str, Any]] = []

    for row in selected:
        idx = row["idx"]
        npz = RETURNS / f"{idx:06d}.npz"
        if not npz.exists():
            continue
        returns = np.load(npz)["ret"].astype(float)
        if returns.size < 60:
            continue
        symbol = row["symbol"]
        if symbol not in close_cache:
            try:
                close_cache[symbol] = kop._load_close(symbol)
            except Exception:
                close_cache[symbol] = pd.Series(dtype=float)
        asset_close = close_cache[symbol]
        if asset_close.empty or len(asset_close) < returns.size:
            continue

        idx_dates = asset_close.index[-returns.size:]
        equity = (1.0 + returns).cumprod() * kop.START_CAPITAL
        strategy_equity = pd.Series(equity, index=idx_dates)
        base = _base_stats(returns)

        variants: list[dict[str, Any]] = []
        for threshold in THRESHOLDS:
            for share in SHARES:
                for ret_share in RETURN_SHARES:
                    result = kop.run_kopilka(
                        strategy_equity, asset_close, btc,
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
                        "btc_share_pct": result["btc_share_pct"],
                        "delta_annual_pct": result["annual_pct"] - base["annual_pct"],
                        "delta_dd_pct": result["max_dd_pct"] - base["max_dd_pct"],
                    })
        out_rows.append({
            "idx": idx, "family": row["family"], "symbol": symbol,
            "risk": row["risk"], "base": base, "variants": variants,
        })

    payload = {
        "date": "2026-10-25",
        "period": {"start": "2021-10-20", "end": "2026-10-19", "years": 5},
        "n_candidates": len(out_rows),
        "thresholds": list(THRESHOLDS),
        "shares": list(SHARES),
        "return_shares": list(RETURN_SHARES),
        "honest_limits": [
            "Сравнение всегда с базой той же строки (без копилки).",
            "Наложение — к реализованной дневной доходности стратегии.",
            "Правило причинное: дно по прошлым барам, будущее не читается.",
        ],
        "rows": out_rows,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str),
                   encoding="utf-8")
    print(f"written: {OUT}")

    # Сводка: сколько раз срабатывало и как менялся результат.
    summary: dict[str, dict[str, Any]] = {}
    for threshold in THRESHOLDS:
        fired = []
        deltas = []
        for entry in out_rows:
            for v in entry["variants"]:
                if v["lock_threshold"] != threshold:
                    continue
                if v["locks"] > 0:
                    fired.append(v["locks"])
                    deltas.append(v["delta_annual_pct"])
        summary[f"{threshold:.2f}"] = {
            "rows_with_any_lock": len(fired),
            "mean_locks": (sum(fired) / len(fired)) if fired else 0.0,
            "mean_delta_annual_pct": (sum(deltas) / len(deltas)) if deltas else 0.0,
            "improved_share": (len([d for d in deltas if d > 0]) / len(deltas)) if deltas else 0.0,
        }
    print("\n| Порог роста | Строк с фиксацией | Среднее фиксаций | Средняя Δ годовой | Доля улучшений |")
    print("|---|---|---|---|---|")
    for threshold in THRESHOLDS:
        s = summary[f"{threshold:.2f}"]
        print(f"| {threshold:.0%} | {s['rows_with_any_lock']} | {s['mean_locks']:.1f} | "
              f"{s['mean_delta_annual_pct']:+.2f} п.п. | {s['improved_share']*100:.0f}% |")


if __name__ == "__main__":
    main()
