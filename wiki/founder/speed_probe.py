"""Замер скорости прогона с включённым кэшем загрузчика.

Зачем: 10000+ прогонов — это вопрос не «сколько стратегий есть», а
«сколько CPU-часов это стоит». Прежний замер дал 3-6 секунд на 5-летний
прогон ТОЛЬКО потому, что данные уже были в кэше процесса; на холодном
диске каждый прогон заново читает CSV.

Этот скрипт меряет оба режима честно:
  1) холодный — каждый прогон читает файл заново;
  2) тёплый — кэш загрузчика включён (VIBE_TRADING_DATA_CACHE=true).

Результат идёт в stdout и решает, какой режим использовать для большой
партии.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(REPO / "wiki" / "founder"))
sys.path.insert(0, str(REPO / "wiki" / "founder" / "archetypes"))

from backtest.engines.crypto import CryptoEngine  # noqa: E402
from backtest.loaders.local_loader import DataLoader as LocalLoader  # noqa: E402
from archetypes.signal_engines import TSMOM  # noqa: E402

START = "2021-10-20"
END = "2026-10-19"


def one_run(loader: LocalLoader, symbol: str, out: Path) -> float:
    cfg = {
        "codes": [symbol], "source": "local",
        "start_date": START, "end_date": END,
        "initial_cash": 10_000.0, "leverage": 1.0, "interval": "1D",
        "perpetual_strict": False, "position_adjustment": "rebalance",
    }
    engine = CryptoEngine(cfg)
    t0 = time.time()
    engine.run_backtest(cfg, loader, TSMOM(lookback=126), out, bars_per_year=365)
    return time.time() - t0


def main() -> None:
    cache_on = os.environ.get("VIBE_TRADING_DATA_CACHE", "").lower() == "true"
    print(f"VIBE_TRADING_DATA_CACHE = {os.environ.get('VIBE_TRADING_DATA_CACHE', '(не задан)')}")
    loader = LocalLoader()
    out_root = Path(os.environ.get("TMPDIR", Path.home())) / "jev-speed-probe"
    out_root.mkdir(parents=True, exist_ok=True)

    symbols = ["SOLUSDT", "BTCUSDT", "ETHUSDT", "ADAUSDT"]
    times = []
    for i, symbol in enumerate(symbols):
        dt = one_run(loader, symbol, out_root / f"probe{i}")
        times.append(dt)
        print(f"  {symbol:10s} {dt:6.2f}s")
    mean = sum(times) / len(times)
    print(f"\nсреднее: {mean:.2f}s на 5-летний прогон  (кэш {'ВКЛ' if cache_on else 'ВЫКЛ'})")
    print(f"1 прогон ≈ {mean:.2f}s; 10000 прогонов на 1 ядре ≈ {10000*mean/3600:.1f} ч")
    print(f"на 8 ядрах (параллельно, ×0.85 потери) ≈ {10000*mean/3600/8*1.15:.1f} ч")


if __name__ == "__main__":
    main()
