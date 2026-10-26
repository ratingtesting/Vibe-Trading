"""Build a multi-symbol crypto panel for Vibe-Trading's Alpha Zoo bench.

The parent project's Binance spot-1d store reaches 2026-10-19 with 384 symbols
of daily bars. Vibe-Trading's ``_load_universe_panel`` knows three universes
(``csi300``, ``sp500``, ``btc-usdt``); none of them is a multi-symbol crypto
basket, so ``bench_runner.run_bench`` refuses to run cross-sectional IC on one
coin. This script does NOT patch Vibe-Trading — it builds the panel the bench
expects and monkey-patches the loader at runtime.

WHAT THE PANEL LOOKS LIKE
``panel`` is a dict whose keys the bench reads directly:
  - ``open`` / ``high`` / ``low`` / ``close`` / ``volume`` — wide ``pd.DataFrame``s
    indexed by date with one column per symbol (the shapes
    ``backtest.loaders`` normally produce).
  - ``_meta`` — the dict ``_prepare_bench_panel`` writes into the panel.
Missing keys fall back to what ``_prepare_bench_panel`` already computes (it
derives ``vwap`` from ``amount``/``volume`` and nothing else is required by the
Alpha Zoo factors — the factors read columns by name, not by attribute).

WHAT THIS DOES NOT DO
- It does not patch Vibe-Trading on disk. The monkey-patch lives inside
  ``run_alpha_zoo_crypto.py`` at run time.
- It does not invent data. Bars are read from the CSVs
  ``binance_json_to_csv.py`` wrote; a missing day is NaN, which the bench
  handles the same way as a delisted symbol.

RUN ORDER
    python binance_json_to_csv.py     # 1. flatten JSON -> CSV (once)
    python build_crypto_panel.py      # 2. CSV -> panel pickle (this file)
    python run_alpha_zoo_crypto.py    # 3. bench on the panel
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

CSV_DIR = Path(r"C:\Projects\jev-vibe\data\binance-spot-1d")
OUT_PICKLE = Path(r"C:\Projects\jev-vibe\data\founder-crypto-panel.pkl")
PANEL_COLUMNS = ("open", "high", "low", "close", "volume")
MIN_SYMBOLS = 10


def build_panel(top_n: int = 40) -> dict[str, pd.DataFrame]:
    """Read the data-bridge CSVs and build the wide panel the bench expects."""
    frames: dict[str, pd.DataFrame] = {}
    for csv_path in sorted(CSV_DIR.glob("*.csv")):
        symbol = csv_path.stem
        frame = pd.read_csv(csv_path, parse_dates=["date"])
        if frame.empty:
            continue
        frame = frame.set_index("date").sort_index()
        frames[symbol] = frame

    if len(frames) < MIN_SYMBOLS:
        raise RuntimeError(f"only {len(frames)} symbols in {CSV_DIR}, need >= {MIN_SYMBOLS}")

    panel: dict[str, pd.DataFrame] = {}
    for column in PANEL_COLUMNS:
        wide = pd.concat(
            {symbol: frame[column] for symbol, frame in frames.items() if column in frame.columns},
            axis=1,
        ).sort_index()
        panel[column] = wide

    panel["_meta"] = {
        "universe": "founder-crypto",
        "source": "binance spot-1d, parent project research/data (2020-2026)",
        "n_symbols": len(frames),
        "date_min": str(panel["close"].index.min().date()),
        "date_max": str(panel["close"].index.max().date()),
    }
    return panel


def main() -> None:
    panel = build_panel()
    close = panel["close"]
    panel["volume"] = panel["volume"].fillna(0.0)
    OUT_PICKLE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PICKLE.open("wb") as handle:
        pickle.dump(panel, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"panel written: {OUT_PICKLE}")
    print(f"  symbols: {panel['_meta']['n_symbols']}")
    print(f"  dates:   {panel['_meta']['date_min']} .. {panel['_meta']['date_max']}")
    print(f"  bars/symbol (median): {int(close.notna().sum().median())}")
    print(f"  close shape: {close.shape}")


if __name__ == "__main__":
    main()
