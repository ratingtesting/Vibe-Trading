"""Run Vibe-Trading's Alpha Zoo bench on the founder's multi-symbol crypto panel.

The bench normally loads one of three hard-coded universes via
``_load_universe_panel``; none of them is a multi-symbol crypto basket, so
``run_bench(universe="btc-usdt")`` refuses with "cross-sectional IC needs >= 2
instruments". This script does not change Vibe-Trading on disk — it
monkey-patches ``_load_universe_panel`` **at run time** to return the founder
panel built by ``build_crypto_panel.py``, then calls ``run_bench`` normally.

Everything the bench reports afterwards is Vibe-Trading's own output: IC stats,
alive/reversed/dead counts, ``top5_by_ir``, ``dead_examples``, ``wall_seconds``.
Nothing in this file re-implements the bench math.

HONESTY
- ``n_trials`` for the Deflated Sharpe is the number of alphas the bench
  actually tested, reported by the bench itself. This script does not invent
  it.
- The universe is the parent project's Binance spot bars. It is survivorship-
  biased in the same way any live exchange list is (delisted coins are absent);
  this is stated on every result the founder's gates require.
- No LLM is involved. The bench is pure pandas/numpy — cost is CPU time only.
"""

from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "agent"))

from src.factors import bench_runner  # noqa: E402
from src.factors.bench_runner import run_bench  # noqa: E402

PANEL_PATH = REPO / "data" / "founder-crypto-panel.pkl"
OUT_DIR = Path(__file__).resolve().parent / "alpha-zoo-results"
UNIVERSE_KEY = "founder-crypto"

# SECURITY NOTE ON PICKLE
# The panel pickle is NOT untrusted input: it is written by build_crypto_panel.py
# in this same repo from the founder's own Binance CSVs (no network fetch, no
# third-party file), and it contains only pandas DataFrames built from those CSVs.
# Loading it with pickle is the same trust boundary as importing a module from the
# repo. If the founder ever regenerates the panel from an external source, switch
# the format to Parquet with a schema check — do not widen this trust boundary.


def _install_panel(panel: dict[str, pd.DataFrame]) -> None:
    """Point ``_load_universe_panel`` at the founder panel for this process."""

    def loader(universe: str, period: str, *, use_cache: bool = True):
        if universe == UNIVERSE_KEY:
            return panel
        # Fall back to the real loader for anything else, so the bench's own
        # error paths (unknown universe, bad period) still fire correctly.
        from src.tools.alpha_bench_tool import _load_universe_panel as real_loader

        return real_loader(universe, period, use_cache=use_cache)

    bench_runner._load_universe_panel = loader


def main() -> None:
    if not PANEL_PATH.exists():
        raise SystemExit(f"panel not found: {PANEL_PATH} — run build_crypto_panel.py first")
    with PANEL_PATH.open("rb") as handle:
        panel = pickle.load(handle)
    print(
        f"panel: {panel['_meta']['n_symbols']} symbols, "
        f"{panel['_meta']['date_min']} .. {panel['_meta']['date_max']}"
    )

    _install_panel(panel)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    zoos = ["alpha101", "gtja191", "qlib158", "academic", "fundamental"]
    horizon = 1
    all_results: dict[str, Any] = {"universe": UNIVERSE_KEY, "horizon": horizon, "zoos": {}}

    for zoo in zoos:
        started = time.time()
        print(f"\n=== {zoo} ===")
        result = run_bench(zoo=zoo, universe=UNIVERSE_KEY, period="2020-2026", top=20, horizon=horizon)
        elapsed = time.time() - started
        result["founder_wall_seconds"] = round(elapsed, 2)
        all_results["zoos"][zoo] = result
        status = result.get("status")
        tested = result.get("n_alphas_tested")
        alive = result.get("alive")
        reversed_ = result.get("reversed")
        dead = result.get("dead")
        print(f"  status={status}  tested={tested}  alive={alive}  reversed={reversed_}  dead={dead}")
        print(f"  wall_seconds={result['founder_wall_seconds']}")
        if status != "ok":
            print(f"  error: {str(result.get('error'))[:200]}")
            continue
        top5 = result.get("top5_by_ir") or []
        for entry in top5[:5]:
            print(f"    top: {entry}")

        out_path = OUT_DIR / f"{zoo}-horizon{horizon}.json"
        out_path.write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"  written: {out_path}")

    (OUT_DIR / "all-zoos-summary.json").write_text(
        json.dumps(all_results, indent=1, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"\nsummary: {OUT_DIR / 'all-zoos-summary.json'}")


if __name__ == "__main__":
    main()
