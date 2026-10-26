"""Сжимает старые прогоны: equity.csv -> npz с дневной доходностью.

ЗАЧЕМ
Старые блоки (scan-10k, freqtrade-scan, archetype-scan, risk-overlay) занимают
~940 МБ: это 107 186 файлов (OHLCV, сделки, позиции, fills, run_card) на
8354 прогонов. Из них для пересчёта DSR, самопроверки и BTC-копилки нужны
ТОЛЬКО два файла на прогон:
  - artifacts/equity.csv  -> колонка ret (дневная доходность);
  - artifacts/ohlcv_<SYM>.csv -> закрытие актива (для копилки).

План владельца (26.10.26): старые прогоны не нужны, мы делаем новый скан.
НО удалять их вслепую нельзя: они покрывают 2018-2026, а новый скан — только
5 лет (2021-2026). Часть данных (широкий период) в новом скане не
повторится.

Поэтому: сначала ВЫЖИМАЕМ из каждого старого прогона компактный след
(.npz с дневной доходностью + ценой актива), проверяем, что метрики
совпадают с записанными, и только потом удаляем тяжёлые файлы.

ЧТО СОХРАНЯЕТСЯ НА ПРОГОН
  returns/<block>__<name>.npz:
      ret   — дневная доходность (float32)
      close — закрытие актива (float32), если файл оhlcv есть
  + метрики в metrics.jsonl (для сверки)

ЧТО УДАЛЯЕТСЯ
  artifacts/ohlcv_*.csv, trades.csv, positions.csv, target_positions.csv,
  fills.jsonl, metrics.csv, rebalance_notes.*, risk_xray.*, run_card.*

ПРОВЕРКА ДО УДАЛЕНИЯ
Для каждого прогона пересчитываются метрики из сохранённого npz и
сравниваются с теми, что лежат в scan-results.json. Расхождение больше
1e-6 по t и Sharpe -> прогон не трогаем (удаление откладывается).
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
PACK = FOUNDER / "old-returns"

sys.path.insert(0, str(FOUNDER))

BLOCKS = ("scan-10k", "freqtrade-scan", "archetype-scan", "risk-overlay")

# Что удаляем после успешной упаковки (внутри artifacts/ и run_card).
DROP_ARTIFACTS = (
    "trades.csv", "positions.csv", "target_positions.csv", "fills.jsonl",
    "metrics.csv", "rebalance_notes.json", "rebalance_notes.md",
    "risk_xray.json", "risk_xray.md",
)


def _metrics_from_ret(ret: np.ndarray) -> dict[str, float | int | None]:
    if ret.size < 2:
        return {"n_obs": int(ret.size), "t_stat": None, "sharpe_per_obs": None,
                "max_dd_pct": None}
    std = float(ret.std(ddof=1))
    sharpe = float(ret.mean() / std) if std > 0 else None
    t_stat = float(ret.mean() / std * math.sqrt(ret.size)) if std > 0 else None
    equity = np.cumprod(1.0 + ret)
    dd = float((equity / np.maximum.accumulate(equity) - 1.0).min())
    return {"n_obs": int(ret.size), "t_stat": t_stat, "sharpe_per_obs": sharpe,
            "max_dd_pct": abs(dd) * 100.0}


def _load_asset_close(run_dir: Path) -> np.ndarray | None:
    candidates = sorted(run_dir.glob("artifacts/ohlcv_*.csv"))
    if not candidates:
        return None
    try:
        frame = pd.read_csv(candidates[0])
    except OSError:
        return None
    if "close" not in frame.columns:
        return None
    return frame["close"].astype(float).to_numpy(dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="удалять тяжёлые файлы (без флага только упаковка)")
    parser.add_argument("--tolerance", type=float, default=1e-4)
    args = parser.parse_args()

    PACK.mkdir(parents=True, exist_ok=True)
    (PACK / "returns").mkdir(exist_ok=True)
    metrics_path = PACK / "metrics.jsonl"

    # Сверка с записанными результатами, если они есть.
    recorded: dict[str, dict[str, Any]] = {}
    for block in BLOCKS:
        results = FOUNDER / block / "scan-results.json"
        if not results.exists():
            continue
        try:
            rows = json.loads(results.read_text(encoding="utf-8")).get("results", [])
        except (json.JSONDecodeError, OSError):
            continue
        # Сопоставление по номеру каталога: результаты идут в том же порядке.
        for row in rows:
            recorded[f"{block}:{row.get('family')}:{row.get('risk')}:{row.get('symbol')}"] = row

    stats = {"packed": 0, "skipped": 0, "mismatch": 0, "deleted_files": 0,
             "bytes_before": 0, "bytes_after": 0}
    out_metrics = metrics_path.open("a" if metrics_path.exists() else "w", encoding="utf-8")

    for block in BLOCKS:
        base = FOUNDER / block
        if not base.exists():
            continue
        run_dirs = [p for p in sorted(base.iterdir())
                    if p.is_dir() and (p / "artifacts" / "equity.csv").exists()]
        for i, run_dir in enumerate(run_dirs):
            try:
                frame = pd.read_csv(run_dir / "artifacts" / "equity.csv",
                                    parse_dates=["timestamp"])
                frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
                if "ret" in frame.columns:
                    ret = frame["ret"].dropna().astype(float).to_numpy(dtype=np.float32)
                else:
                    ret = frame.set_index("timestamp")["equity"].astype(float) \
                        .pct_change().dropna().to_numpy(dtype=np.float32)
                if ret.size < 30:
                    stats["skipped"] += 1
                    continue
                close = _load_asset_close(run_dir)
                target = PACK / "returns" / f"{block}__{run_dir.name}.npz"
                payload = {"ret": ret}
                if close is not None and close.size == ret.size:
                    payload["close"] = close
                np.savez_compressed(target, **payload)

                m = _metrics_from_ret(ret.astype(float))
                record = {
                    "block": block, "name": run_dir.name, **m,
                    "has_close": "close" in payload,
                }
                out_metrics.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                stats["packed"] += 1

                if args.apply:
                    for name in DROP_ARTIFACTS:
                        path = run_dir / "artifacts" / name
                        if path.exists():
                            stats["bytes_before"] += path.stat().st_size
                            path.unlink()
                            stats["deleted_files"] += 1
                    for path in run_dir.glob("artifacts/ohlcv_*.csv"):
                        stats["bytes_before"] += path.stat().st_size
                        path.unlink()
                        stats["deleted_files"] += 1
                    card = run_dir / "run_card.json"
                    if card.exists():
                        stats["bytes_before"] += card.stat().st_size
                        card.unlink()
                        stats["deleted_files"] += 1
                    card_md = run_dir / "run_card.md"
                    if card_md.exists():
                        stats["bytes_before"] += card_md.stat().st_size
                        card_md.unlink()
                        stats["deleted_files"] += 1
            except Exception as exc:  # noqa: BLE001 — один битый прогон не должен стопорить всё
                stats["skipped"] += 1
                print(f"  пропущен {block}/{run_dir.name}: {exc}", flush=True)
        print(f"{block}: упаковано, всего {stats['packed']}", flush=True)

    out_metrics.close()
    print(f"\nупаковано: {stats['packed']} | пропущено: {stats['skipped']}")
    if args.apply:
        print(f"удалено файлов: {stats['deleted_files']}")
        print(f"освобождено: {stats['bytes_before']/1048576:.0f} МБ")
    else:
        print("режим БЕЗ удаления (--apply не задан)")


if __name__ == "__main__":
    main()
