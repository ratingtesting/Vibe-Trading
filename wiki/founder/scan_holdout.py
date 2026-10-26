"""Скан пре-регистрированных семейств на НОВЫХ данных (holdout).

Это ровно тот прогон, который проверяет пре-регистрацию:
  - только те семейства, что зафиксированы в PREREGISTRATION.md;
  - только те параметры, что зафиксированы там же;
  - только тот risk-режим (vol10);
  - окно строго ПОСЛЕ 2026-10-19 - это holdout, которого не видел ни
    один предыдущий шаг.

Ничего не настраивается под результат: и семейства, и окно, и пороги
взять из пре-регистрации.

Сколько holdout нужно: минимум 180 дней (порог из PREREGISTRATION.md).
Пока дней меньше - вердикт будет NO_DATA, и это честный ответ.

Запуск:
    python wiki/founder/scan_holdout.py --workers 7
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(FOUNDER))
sys.path.insert(0, str(FOUNDER / "archetypes"))

from backtest.engines.crypto import CryptoEngine  # noqa: E402
from backtest.loaders.local_loader import DataLoader as LocalLoader  # noqa: E402
from research_metrics import metrics_from_returns  # noqa: E402

import pandas as pd  # noqa: E402

PREREG = FOUNDER / "PREREGISTRATION.md"
OUT = FOUNDER / "holdout"
RESULTS = OUT / "holdout-results.jsonl"

# Правила движка фиксированы (FreqRuleEngine принимает только имя правила),
# поэтому у семейства ровно один вариант. Список соответствует коду
# archetypes/freqtrade_engines.py, и он тоже зафиксирован пре-регистрацией.
FAMILIES: list[str] = ["roc30", "roc10", "ema9_21", "ema21_50", "bb_ride", "donchian20"]
RISK_MODE = "vol10"
HOLD_START = "2026-10-20"


def prereg_families() -> list[str]:
    """Семейства из PREREGISTRATION.md - не отсюда, а оттуда."""
    text = PREREG.read_text(encoding="utf-8")
    out: list[str] = []
    for line in text.splitlines():
        match = re.match(r"\| \*\*([a-z0-9_]+)\*\* \| [AB]:", line)
        if match:
            out.append(match.group(1))
    return out


def prereg_min_days() -> int:
    text = PREREG.read_text(encoding="utf-8")
    match = re.search(r"Дней holdout, не меньше \| (\d+)", text)
    return int(match.group(1)) if match else 180


def build_jobs(families: list[str], symbols: list[str]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for family in families:
        for symbol in symbols:
            jobs.append({"family": family, "params": {},
                         "symbol": symbol, "risk": RISK_MODE})
    return jobs


def _engine_for(family: str, params: dict[str, Any]):
    from archetypes.freqtrade_engines import FreqRuleEngine
    from archetypes.signal_engines import VolTargeted

    return VolTargeted(FreqRuleEngine(family), target_vol=0.10)


def run_job(job: dict[str, Any], idx: int, start: str, end: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "idx": idx, "family": job["family"], "symbol": job["symbol"],
        "risk": job["risk"], "params": job["params"], "status": "ERROR",
    }
    run_dir = OUT / "runs" / f"{idx:06d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "codes": [job["symbol"]], "source": "local",
        "start_date": start, "end_date": end,
        "initial_cash": 10_000.0, "leverage": 1.0, "interval": "1D",
        "perpetual_strict": False, "position_adjustment": "rebalance",
    }
    try:
        loader = LocalLoader()
        market = CryptoEngine(config)
        engine = _engine_for(job["family"], job["params"])
        with contextlib.redirect_stdout(io.StringIO()):
            metrics = market.run_backtest(config, loader, engine, run_dir,
                                          bars_per_year=365)
        frame = pd.read_csv(run_dir / "artifacts" / "equity.csv", parse_dates=["timestamp"])
        frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
        returns = frame["ret"].dropna().astype(float)
        m = metrics_from_returns(returns)
        row.update({
            "status": "OK", "n_obs": m.n_obs, "annual_pct": m.annual_pct,
            "max_dd_pct": m.max_dd_pct, "t_stat": m.t_stat,
            "sharpe_per_obs": m.sharpe_per_observation,
            "skew": m.skew, "kurtosis": m.kurtosis,
            "trade_count": metrics.get("trade_count"),
            "final_value": metrics.get("final_value"),
        })
    except Exception as exc:  # noqa: BLE001 — один битый прогон не стопорит всё
        row["error"] = str(exc)[:200]
    return row


def _worker(payload: tuple[dict[str, Any], int, str, str]) -> dict[str, Any]:
    job, idx, start, end = payload
    return run_job(job, idx, start, end)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--end", default="")
    args = parser.parse_args()

    families = prereg_families()
    min_days = prereg_min_days()
    print(f"пре-регистрация: семейства {families}")
    print(f"минимум дней holdout: {min_days}")

    # Пара: только те, что есть в data-bridge конфиге - иначе загрузчик
    # их не отдаёт ("no config entry for symbol"). Конфиг содержит 144 пары
    # из 384 скачанных файлов.
    import yaml

    bridge = Path.home() / ".vibe-trading" / "data-bridge" / "config.yaml"
    allowed: set[str] = set()
    if bridge.exists():
        config = yaml.safe_load(bridge.read_text(encoding="utf-8")) or {}
        for source in config.get("sources", []) or []:
            symbol = source.get("symbol")
            if symbol:
                allowed.add(symbol)
    print(f"пар в data-bridge: {len(allowed)}")

    data_dir = REPO / "data" / "binance-spot-1d"
    symbols: list[str] = []
    last_dates: list[str] = []
    for path in sorted(data_dir.glob("*.csv")):
        if allowed and path.stem not in allowed:
            continue
        try:
            frame = pd.read_csv(path, parse_dates=["date"])
        except Exception:
            continue
        if frame.empty:
            continue
        last = frame["date"].max().date().isoformat()
        symbols.append(path.stem)
        last_dates.append(last)
    if not symbols:
        print("нет данных")
        return
    newest = max(last_dates)
    end = args.end or newest
    print(f"пар с данными: {len(symbols)}, самый свежий бар: {newest}, окно: {HOLD_START}..{end}")

    jobs = build_jobs(families, symbols)
    if args.limit:
        jobs = jobs[:args.limit]
    print(f"прогонов: {len(jobs)}")

    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    ok = err = 0
    with RESULTS.open("w", encoding="utf-8") as sink, \
            ProcessPoolExecutor(max_workers=args.workers) as pool:
        payloads = [(job, idx, HOLD_START, end) for idx, job in enumerate(jobs)]
        futures = {pool.submit(_worker, p): p[0] for p in payloads}
        for i, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            sink.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            sink.flush()
            if row["status"] == "OK":
                ok += 1
            else:
                err += 1
            if i % 50 == 0:
                print(f"  {i}/{len(jobs)} ok={ok} err={err} "
                      f"{time.time()-started:.0f}s", flush=True)

    print(f"\nготово: ok={ok} err={err} за {time.time()-started:.0f}s")
    print(f"written: {RESULTS}")


if __name__ == "__main__":
    main()
