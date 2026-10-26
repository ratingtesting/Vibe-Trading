"""Большой скан: 10000+ прогонов за 5 ЛЕТ, доходность в ГОДОВЫХ.

ЗАЧЕМ ЭТОТ ФАЙЛ
Владелец (25.10.26): «10000 надо прогнать снова». Прежние блоки смотрели на
разные окна и считали по-разному; теперь один скан с одним правилом.

ЧТО ФИКСИРУЕТСЯ ЖЁСТКО (иначе числа несопоставимы)
1. ПЕРИОД: 2021-10-20 .. 2026-10-19 = ровно 5 лет, 1826 дневных баров.
   Все прогоны — один и тот же интервал. Символы с недостаточной историей
   в этот скан не попадают (фильтр по числу баров), чтобы не сравнивать
   стратегии с разной длиной выборки.
2. ДОХОДНОСТЬ В ГОДОВЫХ: считается из дневной доходности по формуле
   (prod(1+r))^(365/n) - 1, где n — число наблюдений. Для 1826 баров это
   ровно 5 лет сложного процента. Никаких «годовых» делений на глаз.
3. ЕДИНАЯ ШКАЛА МЕТРИК: research_metrics.metrics_from_returns —
   периодный Sharpe (для DSR), t со знаком, просадка как величина потери,
   реальные skew/kurtosis.
4. ИСПОЛНЕНИЕ РАЗМЕРА: position_adjustment="rebalance" — иначе vol-оверлеи
   считают то, что никогда не исполнялось (1885 из 2180 запросов на
   roc10-vol10-AVAX в режиме hold).

ЭКОНОМИЯ ДИСКА
Диск машины заполнен на 97%. Полный набор артефактов (~90 КБ на прогон)
на 12000 прогонов — это ~1 ГБ, а на диске свободно 4.8 ГБ. Поэтому после
каждого прогона скан ОСТАВЛЯЕТ ТОЛЬКО компактный .npz с дневной
доходностью и метриками, а тяжёлые CSV (ohlcv, fills, trades, positions)
удаляет. Полный набор артефактов сохраняется только для строк-кандидатов
(отбор после прогона).

ЗАПИСЬ
wiki/founder/scan5y/scan-results.jsonl  — по строке на прогон
wiki/founder/scan5y/returns/           — .npz с дневной доходностью
wiki/founder/scan5y/scan-results.json  — сводка
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OUT = FOUNDER / "scan5y"

sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(FOUNDER))
sys.path.insert(0, str(FOUNDER / "archetypes"))

# --- ОКНО ---------------------------------------------------------------
START_DATE = "2021-10-20"
END_DATE = "2026-10-19"
MIN_BARS = 1826          # ровно 5 лет дневных баров
ANNUALISATION = 365.0

# --- СЕМЕЙСТВА ----------------------------------------------------------
# Те же 67 архетипных вариантов + 21 правило freqtrade, что и в прежних
# блоках: перебор расширяется ЧИСЛОМ ПАР, а не новыми правилами, чтобы
# пул оставался интерпретируемым.
from archetype_grid import VARIANTS  # noqa: E402
from freqtrade_engines import RULES  # noqa: E402


def risk_modes() -> list[tuple[str, str]]:
    """(имя режима, тип) — тип: raw | vol10 | vol12dd820."""
    return [("raw", "raw"), ("vol10", "vol10"), ("vol12dd820", "vol12dd820")]


def symbols_with_history() -> list[str]:
    """Символы с >= MIN_BARS дневных баров в локальном хранилище."""
    csv_dir = REPO / "data" / "binance-spot-1d"
    out: list[str] = []
    for path in csv_dir.glob("*.csv"):
        try:
            with path.open(encoding="utf-8") as fh:
                lines = sum(1 for _ in fh) - 1
        except OSError:
            continue
        if lines >= MIN_BARS:
            out.append(path.stem)
    out.sort()
    return out


def build_jobs(max_symbols: int | None) -> list[dict[str, Any]]:
    """Полный список прогонов: вариант x риск x символ.

    ПОРЯДОК ПРИНЦИПИАЛЕН. Первые N прогонов должны покрывать ВСЕ семейства
    равномерно, а не выжигать одно семейство на всех парах. Поэтому после
    построения список перемешивается «раунд- robin» по группам
    (вариант x риск): каждый следующий блок берёт по одному прогону от
    каждой группы. Иначе за первые 10 000 строк покрытие было бы 2-3
    вариантами из 88, и пришлось бы ждать все 35 000 ради вывода.
    """
    syms = symbols_with_history()
    if max_symbols:
        syms = syms[:max_symbols]
    groups: list[list[dict[str, Any]]] = []
    for family, plist in VARIANTS.items():
        for params in plist:
            for risk_name, risk_type in risk_modes():
                group = [
                    {
                        "family": family, "params": params, "risk": risk_name,
                        "risk_type": risk_type, "symbol": symbol,
                    }
                    for symbol in syms
                ]
                groups.append(group)
    for rule in RULES:
        for risk_name, risk_type in (("raw", "raw"), ("vol10", "vol10")):
            group = [
                {
                    "family": f"ft_{rule}", "params": {}, "risk": risk_name,
                    "risk_type": risk_type, "symbol": symbol,
                }
                for symbol in syms
            ]
            groups.append(group)

    # ПОРЯДОК. Нужен префикс, который покрывает И все семейства, И много
    # пар. Берём слот пары = (позиция_пары + группа // 8) % len(syms) и
    # сортируем по (слот, группа): каждый блок из ~243 прогонов покрывает
    # все 243 варианта-риска и около 30 пар. Через 12 блоков (3000 строк)
    # покрыты все 144 пары и все семейства — промежуточный отчёт можно
    # давать, не дожидаясь всех 35 000.
    flat: list[tuple[int, int, dict[str, Any]]] = []
    for group_index, group in enumerate(groups):
        for symbol_index, job in enumerate(group):
            slot = (symbol_index + group_index // 8) % len(syms)
            flat.append((slot, group_index, job))
    flat.sort(key=lambda item: (item[0], item[1]))
    return [job for _slot, _group, job in flat]


MANIFEST = OUT / "jobs-manifest.json"


def _write_manifest(jobs: list[dict[str, Any]]) -> None:
    """Стабильный манифест: индекс прогона не должен зависеть от порядка запуска."""
    MANIFEST.write_text(
        json.dumps(jobs, ensure_ascii=False, default=str), encoding="utf-8")


# --- РАБОТНИК -----------------------------------------------------------

def _worker(payload: tuple[int, dict[str, Any]]) -> dict[str, Any]:
    """Один прогон. Возвращает метрики; тяжёлые артефакты удаляет."""
    idx, job = payload
    import contextlib
    import io

    from backtest.engines.crypto import CryptoEngine
    from backtest.loaders.local_loader import DataLoader as LocalLoader
    from archetypes.signal_engines import (
        DrawdownThrottled,
        MARegimeFilter,
        RegimeSwitching,
        TSMOM,
        VolTargeted,
        VolatilityBreakout,
        ZScoreMeanReversion,
    )
    from freqtrade_engines import FreqRuleEngine
    from research_metrics import metrics_from_returns
    import pandas as pd

    family = job["family"]
    symbol = job["symbol"]
    risk_type = job["risk_type"]

    if family.startswith("ft_"):
        base = FreqRuleEngine(family[3:])
    else:
        cls = {
            "TSMOM": TSMOM, "MARegimeFilter": MARegimeFilter,
            "VolatilityBreakout": VolatilityBreakout,
            "ZScoreMeanReversion": ZScoreMeanReversion,
            "RegimeSwitching": RegimeSwitching,
        }[family]
        base = cls(**job["params"])

    if risk_type == "raw":
        engine = base
    elif risk_type == "vol10":
        engine = VolTargeted(base, target_vol=0.10)
    else:
        engine = DrawdownThrottled(
            VolTargeted(base, target_vol=0.12), soft_dd=0.08, hard_dd=0.20
        )

    run_dir = OUT / "runs" / f"{idx:06d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "codes": [symbol], "source": "local",
        "start_date": START_DATE, "end_date": END_DATE,
        "initial_cash": 10_000.0, "leverage": 1.0, "interval": "1D",
        "perpetual_strict": False,
        "position_adjustment": "rebalance",
    }
    row: dict[str, Any] = {
        "idx": idx, "family": family, "symbol": symbol, "risk": job["risk"],
        "params": job["params"], "status": "ERROR",
    }
    try:
        loader = LocalLoader()
        market = CryptoEngine(config)
        # Движок печатает JSON метрик в stdout — на 35k прогонов это
        # миллионы строк в лог и заметная потеря времени. Подавляем вывод:
        # метрики всё равно читаются из run_card/equity.csv.
        with contextlib.redirect_stdout(io.StringIO()):
            metrics = market.run_backtest(config, loader, engine, run_dir, bars_per_year=365)
        frame = pd.read_csv(run_dir / "artifacts" / "equity.csv", parse_dates=["timestamp"])
        frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
        returns = frame["ret"].dropna().astype(float)
        m = metrics_from_returns(returns)
        row.update({
            "status": "OK",
            "n_obs": m.n_obs,
            "annual_pct": m.annual_pct,
            "max_dd_pct": m.max_dd_pct,
            "t_stat": m.t_stat,
            "sharpe_per_obs": m.sharpe_per_observation,
            "sharpe_annual": m.sharpe_annual,
            "skew": m.skew,
            "kurtosis": m.kurtosis,
            "trade_count": metrics.get("trade_count"),
            "dropped_target_adjustment_count": metrics.get("dropped_target_adjustment_count"),
            "rebalance_executed_fills": metrics.get("rebalance_executed_fills"),
            "final_value": metrics.get("final_value"),
        })
        # Компактный след: дневная доходность нужна для DSR и для BTC-копилки.
        np.savez_compressed(
            OUT / "returns" / f"{idx:06d}.npz",
            ret=returns.to_numpy(dtype=np.float32),
        )
    except Exception as exc:  # noqa: BLE001 — одна ошибка не должна убить партию
        row["error"] = str(exc)[:200]
    finally:
        # Тяжёлые артефакты не нужны для 10000 прогонов: диск заполнен.
        shutil.rmtree(run_dir, ignore_errors=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "returns").mkdir(exist_ok=True)
    (OUT / "runs").mkdir(exist_ok=True)
    results_path = OUT / "scan-results.jsonl"

    jobs = build_jobs(args.max_symbols or None)
    if args.limit:
        jobs = jobs[: args.limit]
    total = len(jobs)
    symbols = len({j["symbol"] for j in jobs})
    variants = len({(j["family"], json.dumps(j["params"], sort_keys=True)) for j in jobs})
    print(f"scan5y: {total} прогонов = {variants} вариантов x {len(risk_modes())} рисков x {symbols} пар")
    print(f"окно: {START_DATE}..{END_DATE} (5 лет, >= {MIN_BARS} баров)  workers: {args.workers}")

    # Resume по МАНИФЕСТУ: индекс в jsonl нельзя считать «сколько уже
    # посчитано» — строки могли прийти не по порядку, а после перезапуска
    # порядок меняется. Resume по индексу, присутствующему в артефакте.
    done_idx: set[int] = set()
    if args.resume and results_path.exists():
        with results_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    done_idx.add(int(json.loads(line)["idx"]))
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
        print(f"resume: уже посчитано {len(done_idx)} прогонов")
    _write_manifest(jobs)

    started = time.time()
    ok = 0
    err = 0
    from concurrent.futures import ProcessPoolExecutor, as_completed

    todo = [(i, jobs[i]) for i in range(total) if i not in done_idx]
    with results_path.open("a" if args.resume else "w", encoding="utf-8") as sink, \
            ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {}
        for i, job in todo:
            futures[pool.submit(_worker, (i, job))] = i
            if len(futures) >= args.workers * 4:
                for fut in as_completed(list(futures)):
                    row = fut.result()
                    sink.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                    if row.get("status") == "OK":
                        ok += 1
                    else:
                        err += 1
                    futures.pop(fut)
                sink.flush()
                n = ok + err
                elapsed = time.time() - started
                rate = n / elapsed if elapsed else 0
                eta = (len(todo) - n) / rate if rate else 0
                print(f"  {n}/{len(todo)} ok={ok} err={err} {elapsed:.0f}s "
                      f"({rate:.2f}/s) ETA {eta/60:.0f} min", flush=True)
        for fut in as_completed(list(futures)):
            row = fut.result()
            sink.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            if row.get("status") == "OK":
                ok += 1
            else:
                err += 1
    elapsed = time.time() - started

    summary = {
        "date": "2026-10-25",
        "period": {"start": START_DATE, "end": END_DATE, "years": 5, "min_bars": MIN_BARS},
        "annualisation": ANNUALISATION,
        "position_adjustment": "rebalance",
        "n_jobs": total,
        "n_ok_this_run": ok,
        "n_error_this_run": err,
        "n_resumed": len(done_idx),
        "n_variants": variants,
        "n_symbols": symbols,
        "elapsed_s": round(elapsed, 1),
        "note": "Доходность в годовых = (prod(1+r))^(365/n)-1 из дневной доходности.",
    }
    (OUT / "scan-summary.json").write_text(
        json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nготово: ok={ok} err={err} за {elapsed:.0f}s")
    print(f"written: {results_path}")
    print(f"written: {OUT / 'scan-summary.json'}")


if __name__ == "__main__":
    main()
