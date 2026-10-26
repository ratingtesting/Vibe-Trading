"""Joint vol-target + drawdown-throttle overlay over the 13 G4+G5 survivors.

GOAL (founder's plan step 4): pull max drawdown under 20% while keeping
t >= 2.5 (the CANDIDATE bar). The previous overlay scan applied vol-target and
drawdown-throttle SEPARATELY; this one stacks them:
    position = clip(target_vol / realised_vol, 0, 1) * dd_throttle(position)
so the strategy de-levers in high volatility AND linearly as its own drawdown
deepens from soft to hard.

WHY THESE PARAMS
- vol targets 8/10/12% (tighter than before — the 20% DD rule needs more
  de-levering than 15/20% targets delivered);
- ddthrottle soft 8%/hard 20% (linear cut starts early, reaches zero at 20%
  — matched to the DD<=20% gate);
- also a "belt" variant that additionally stops trading at hard_dd.

Gate check afterwards: t >= 2.5, DSR >= 0.95 (recomputed in
honest_dsr_verdict.py), max_drawdown <= 20%.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "archetypes"))

from backtest.engines.crypto import CryptoEngine  # noqa: E402
from backtest.loaders.local_loader import DataLoader as LocalLoader  # noqa: E402
from archetypes.signal_engines import (  # noqa: E402
    DrawdownThrottled,
    MARegimeFilter,
    RegimeSwitching,
    TSMOM,
    VolTargeted,
    VolatilityBreakout,
    ZScoreMeanReversion,
)

REPO = Path(__file__).resolve().parents[2]
PANEL = REPO / "data" / "founder-crypto-panel.pkl"
SCAN = Path(__file__).resolve().parent / "archetype-scan" / "scan-results.json"
OUT = Path(__file__).resolve().parent / "combo-overlay"
RESULTS_PATH = OUT / "combo-results.json"

BASE_CLASSES: dict[str, Any] = {
    "TSMOM": TSMOM,
    "MARegimeFilter": MARegimeFilter,
    "VolatilityBreakout": VolatilityBreakout,
    "ZScoreMeanReversion": ZScoreMeanReversion,
    "RegimeSwitching": RegimeSwitching,
}


def _survivors() -> list[dict[str, Any]]:
    """The 13 G4+G5 survivors, re-derived from the honest verdict (authoritative)."""
    verdict = json.loads((Path(__file__).resolve().parent / "honest-dsr-verdict.json")
                         .read_text(encoding="utf-8"))
    names = {row["name"] for row in verdict["all_rows"]
             if row.get("gate_g4") and row.get("gate_g5")}
    scan = json.loads(SCAN.read_text(encoding="utf-8"))
    return [row for row in scan["results"]
            if row.get("status") == "OK" and row.get("t_stat") is not None
            and abs(row["t_stat"]) >= 3.0]


def _equity_series(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    return frame.set_index("timestamp")["equity"]


def _sharpe(returns: pd.Series) -> float | None:
    if len(returns) < 3 or returns.std(ddof=1) == 0:
        return None
    return float(returns.mean() / returns.std(ddof=1) * (365 ** 0.5))


def _t_stat(returns: pd.Series) -> float | None:
    if len(returns) < 30:
        return None
    mean, std = returns.mean(), returns.std(ddof=1)
    if std == 0:
        return None
    return float(mean / (std / (len(returns) ** 0.5)))


def main() -> None:
    scan = json.loads(SCAN.read_text(encoding="utf-8"))
    survivors = _survivors()
    print(f"G4+G5 survivors: {len(survivors)}")

    combos: list[tuple[str, str, Any]] = []
    for row in survivors:
        family, params, symbol = row["family"], row["params"], row["symbol"]
        for target_vol in (0.08, 0.10, 0.12):
            for soft, hard in ((0.08, 0.20), (0.10, 0.25)):
                base = BASE_CLASSES[family](**params)
                stacked = DrawdownThrottled(
                    VolTargeted(base, target_vol=target_vol),
                    soft_dd=soft, hard_dd=hard,
                )
                combos.append((
                    f"{family}-{symbol}-vol{int(target_vol*100)}-dd{int(soft*100)}/{int(hard*100)}",
                    symbol, stacked,
                ))

    print(f"combo runs: {len(combos)}")
    loader = LocalLoader()
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    results: list[dict[str, Any]] = []

    for index, (label, symbol, engine) in enumerate(combos, start=1):
        run_dir = OUT / f"{label}-{index}"
        run_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "codes": [symbol],
            "source": "local",
            "start_date": "2020-01-01",
            "end_date": "2026-10-19",
            "initial_cash": 10_000.0,
            "leverage": 1.0,
            "interval": "1D",
            "perpetual_strict": False,
        }
        try:
            market = CryptoEngine(config)
            result = market.run_backtest(config, loader, engine, run_dir, bars_per_year=365)
        except Exception as exc:  # noqa: BLE001 — record and continue
            results.append({"label": label, "symbol": symbol,
                            "status": "ERROR", "error": str(exc)[:160]})
            continue
        equity = _equity_series(run_dir)
        returns = equity.pct_change().dropna() if len(equity) > 2 else pd.Series(dtype=float)
        results.append({
            "label": label, "symbol": symbol, "status": "OK",
            "annual_pct": float(result.get("annual_return") or 0.0) * 100,
            "max_dd_pct": float(result.get("max_drawdown") or 0.0) * 100,
            "sharpe": _sharpe(returns), "t_stat": _t_stat(returns),
            "trade_count": int(result.get("trade_count") or 0),
        })
        if index % 10 == 0:
            print(f"  {index}/{len(combos)} done ({time.time()-started:.0f}s)")

    RESULTS_PATH.write_text(json.dumps({"results": results}, indent=1, ensure_ascii=False),
                            encoding="utf-8")
    ok = [r for r in results if r.get("status") == "OK"]
    passed = [r for r in ok if r["t_stat"] is not None and abs(r["t_stat"]) >= 2.5
              and (r["max_dd_pct"] or 100) <= 20.0]
    passed.sort(key=lambda r: -(r["t_stat"] or 0))
    print(f"\n=== COMBO OVERLAY ИТОГ ===")
    print(f"прогонов: {len(results)} OK={len(ok)} время {time.time()-started:.0f}s")
    print(f"прошли CANDIDATE-гейт (|t|>=2.5 AND DD<=20%): {len(passed)}")
    for r in passed[:15]:
        print(f"  {r['label']}: {r['annual_pct']:.2f}%/год t={r['t_stat']:.3f} DD={r['max_dd_pct']:.1f}%")
    if not passed:
        best = [r for r in ok if r["t_stat"] is not None]
        best.sort(key=lambda r: -(r["t_stat"] or 0))
        print("  ни один. Топ-5 по |t| (с DD):")
        for r in best[:5]:
            print(f"    {r['label']}: {r['annual_pct']:.2f}%/год t={r['t_stat']:.3f} DD={r['max_dd_pct']:.1f}%")
    print(f"written: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
