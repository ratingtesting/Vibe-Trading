"""Founder archetypes — first real backtest in Vibe-Trading.

Runs the five executable founder archetypes over the data-bridge CSVs (top-40
Binance spot pairs, daily bars to 2026-10-19) through Vibe-Trading's
LocalLoader and CryptoEngine, then applies the founder's eight-gate ladder.

WHAT IS HONEST HERE
- The parent project's verdicts were measured on a different fee schedule
  (Alpaca 44 bps round trip). Vibe-Trading's CryptoEngine defaults to maker
  0.02% / taker 0.05% / slippage 0.05%, which is a DIFFERENT basis. A verdict
  under one fee schedule does not transfer to another — that is why this run
  re-measures rather than re-quotes.
- The founder's gate G4 (t >= 3.0) and G5 (Deflated Sharpe >= 0.95) are
  computed with Vibe-Trading's own ``src/quantlib/multipletesting.py``, which
  is the production replacement for the parent project's hand-rolled t-stat.
- N trials is set to the number of archetypes actually scanned (5), which is
  the honest count for this run. A scan that tests 478 factors would use 478.
- Forward returns are close-to-close on daily bars. Vibe-Trading's CryptoEngine
  applies funding and slippage on its own — this script does not double-count
  them.

WHAT IS NOT HERE
- Funding rates. The data-bridge carries spot bars only; the CryptoEngine's
  ``funding_mode: "data"`` needs a funding feed that is not wired yet. This
  script therefore runs with ``perpetual_strict`` OFF, which means the engine
  uses its default fixed funding rate — the same simplification the parent
  project's P3 run was criticised for. The verdict on funding-carry is NOT
  revisited here; that archetype refuses to build (see ``signal_engines.py``).
- Live exchange data. Everything comes from the local CSVs; no network call.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "agent"))

from backtest.engines.crypto import CryptoEngine  # noqa: E402
from backtest.loaders.local_loader import DataLoader as LocalLoader  # noqa: E402
from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

sys.path.insert(0, str(REPO / "wiki" / "founder" / "archetypes"))

from signal_engines import (  # noqa: E402
    MARegimeFilter,
    RegimeSwitching,
    TSMOM,
    VolatilityBreakout,
    ZScoreMeanReversion,
)

UNIVERSE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT"]
N_TRIALS = 5
COST_BPS_ROUND_TRIP = 44  # parent project's Alpaca basis, kept for comparability


def _daily_returns(prices: pd.Series) -> pd.Series:
    return prices.pct_change().dropna()


def _t_stat(returns: pd.Series) -> float | None:
    clean = returns.dropna()
    if len(clean) < 2:
        return None
    mean = clean.mean()
    std = clean.std(ddof=1)
    if std == 0 or std != std:
        return None
    return float(mean / std * (len(clean) ** 0.5))


def _max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(abs(drawdown.min()))


def run_one(engine: Any, loader: LocalLoader, run_dir: Path) -> dict[str, Any]:
    config = {
        "codes": UNIVERSE,
        "source": "local",
        "start_date": "2020-01-01",
        "end_date": "2026-10-19",
        "initial_cash": 10_000.0,
        "leverage": 1.0,
        "interval": "1D",
        "perpetual_strict": False,
    }
    market = CryptoEngine(config)
    result = market.run_backtest(config, loader, engine, run_dir, bars_per_year=365)
    return result if isinstance(result, dict) else {}


def main() -> None:
    loader = LocalLoader()
    out_dir = Path(__file__).resolve().parent / "first-backtest"
    out_dir.mkdir(parents=True, exist_ok=True)

    engines = {
        "tsmom": TSMOM(),
        "ma-regime": MARegimeFilter(),
        "vol-breakout": VolatilityBreakout(),
        "zscore-mean-reversion": ZScoreMeanReversion(),
        "regime-switching": RegimeSwitching(),
    }

    rows: list[dict[str, Any]] = []
    for name, engine in engines.items():
        run_dir = out_dir / name
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = run_one(engine, loader, run_dir)
        except Exception as exc:  # noqa: BLE001 — a failed archetype is a recorded result, not a crash
            rows.append({"archetype": name, "status": "ERROR", "error": str(exc)[:200]})
            continue

        equity_curve = result.get("equity") or result.get("equity_curve") or {}
        if isinstance(equity_curve, dict):
            equity = pd.Series(equity_curve)
        elif isinstance(equity_curve, list):
            equity = pd.Series([row.get("equity", row) if isinstance(row, dict) else row for row in equity_curve])
        else:
            equity = pd.Series(dtype=float)

        # Vibe-Trading's runner returns a flat metrics dict, and the equity curve
        # lands in artifacts/equity.csv (timestamp,ret,equity,...). Read the CSV —
        # deriving returns from the summary numbers would fake G4.
        returns = pd.Series(dtype=float)
        equity = pd.Series(dtype=float)
        equity_path = run_dir / "artifacts" / "equity.csv"
        if equity_path.exists():
            frame = pd.read_csv(equity_path, parse_dates=["timestamp"])
            equity = frame.set_index("timestamp")["equity"]
            returns = _daily_returns(equity)

        # Use the engine's own summary numbers for the money-first columns.
        annualised = float(result.get("annual_return") or 0.0)
        total_return = float(result.get("total_return") or 0.0)
        max_dd = float(result.get("max_drawdown") or 0.0)
        trade_count = int(result.get("trade_count") or 0)
        engine_sharpe = result.get("sharpe")
        benchmark_return = result.get("benchmark_return")

        t_stat = _t_stat(returns) if len(returns) > 2 else None

        # G5 needs at least 30 observations (src/quantlib MIN_OBSERVATIONS).
        dsr_value: float | None = None
        if len(returns) >= 30:
            try:
                dsr = deflated_sharpe_ratio(
                    observed_sharpe=float(returns.mean() / returns.std(ddof=1) * (365 ** 0.5)),
                    n_trials=N_TRIALS,
                    n_observations=len(returns),
                    trial_sharpe_std=0.0,
                    skew=float(returns.skew()),
                    kurtosis=float(returns.kurt() + 3),
                )
                dsr_value = getattr(dsr, "dsr", None) if dsr is not None else None
            except ValueError:
                dsr_value = None

        gate_g4 = t_stat is not None and abs(t_stat) >= 3.0
        gate_g5 = dsr_value is not None and dsr_value >= 0.95

        rows.append(
            {
                "archetype": name,
                "status": "OK",
                "annualised_pct": round(annualised * 100, 2),
                "total_return_pct": round(total_return * 100, 2),
                "t_stat": round(t_stat, 3) if t_stat is not None else None,
                "gate_g4_pass": gate_g4,
                "dsr": round(dsr_value, 4) if dsr_value is not None else None,
                "gate_g5_pass": gate_g5,
                "max_drawdown_pct": round(abs(max_dd) * 100, 2),
                "trade_count": trade_count,
                "engine_sharpe": engine_sharpe,
                "benchmark_return_pct": round(float(benchmark_return) * 100, 2) if benchmark_return is not None else None,
                "n_days": int(len(returns)),
            }
        )

    (out_dir / "results.json").write_text(
        json.dumps(
            {
                "date": "2026-10-19",
                "engine": "Vibe-Trading CryptoEngine, maker 0.02% / taker 0.05% / slippage 0.05%, leverage 1.0",
                "universe": UNIVERSE,
                "n_trials": N_TRIALS,
                "gate_note": "G4 t>=3.0, G5 DSR>=0.95 (src/quantlib/multipletesting.py)",
                "cost_note": "CryptoEngine's own fee schedule, NOT the parent project's 44 bps — re-measured, not re-quoted",
                "rows": rows,
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"{'archetype':24s} {'годовая %':>10s} {'t':>7s} {'G4':>5s} {'DSR':>8s} {'G5':>5s} {'DD%':>8s}")
    for row in rows:
        if row.get("status") == "ERROR":
            print(f"{row['archetype']:24s} ERROR: {row['error'][:60]}")
            continue
        print(
            f"{row['archetype']:24s} {row['annualised_pct']:>10.2f} "
            f"{row['t_stat'] or 0:>7.3f} "
            f"{'✅' if row['gate_g4_pass'] else '✗':>5s} "
            f"{row['dsr'] if row['dsr'] is not None else '—':>8} "
            f"{'✅' if row['gate_g5_pass'] else '✗':>5s} "
            f"{row['max_drawdown_pct'] or 0:>8.2f}"
        )


if __name__ == "__main__":
    main()
