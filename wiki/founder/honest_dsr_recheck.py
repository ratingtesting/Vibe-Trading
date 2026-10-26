"""Честный пересчёт DSR по ВСЕМ прогонам, что лежат на диске.

ЧТО ИСПРАВЛЯЕТ ЭТОТ ФАЙЛ (три дефекта, найденных мат-аудитом 2026-10-24):

C1. DSR считался с ГОДОВЫМ Sharpe (mean/std * sqrt(365)), а
    src/quantlib/multipletesting.py требует ПОПЕРИОДНЫЙ (mean/std).
    Годовой Sharpe завышал DSR примерно в sqrt(365) раз. Все прежние
    «DSR=0.9998» и «13 выживших» — НЕВЕРИФИЦИРОВАНЫ.
    Здесь: sharpe = mean(ret)/std(ret), без аннуализации.

C2. Гейт просадки. В scan_10k.py стояло `max_dd_pct <= 20`, а просадка
    отрицательная — любое отрицательное число проходило. Канон:
    просадка не хуже 20% это |dd| <= 20.

C3. skew/kurtosis подавались заглушками (0.0 / 3.0) вместо реальных
    моментов доходности. Здесь считаются по реальному ряду.
    Kurtosis — НЕэксцессовая (3 для гауссова).

ЧТО СЧИТАЕТСЯ
Единица теста — один прогон. Пул испытаний — ВСЕ прогоны на диске:
scan-10k (6030) + freqtrade-scan (1260) + archetype-scan (1020) +
risk-overlay (44) = 8354. n_trials = размер пула, trial_sharpe_std —
разброс Sharpe по всему пулу в ТОЙ ЖЕ периодической шкале.

ЧТО ЭТО НЕ ДЕЛАЕТ
Не переобучает и не перезапускает бэктесты: читает уже записанные
artifacts/equity.csv. Не объявляет новых «единственных PASS» — только
честный пересчёт уже опубликованных чисел в правильной шкале.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OUT = FOUNDER / "honest-dsr-recheck.json"

sys.path.insert(0, str(REPO / "agent"))
sys.path.insert(0, str(FOUNDER))
sys.path.insert(0, str(FOUNDER / "archetypes"))

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

GAUSSIAN_KURTOSIS = 3.0
MIN_OBS = 30

# Канон владельца: ЭТАЛОН = t>=3 + DSR>=0.95 + DD<=20%;
#                 КАНДИДАТ = t>=2.5 + DSR>=0.95 + DD<=20%.
REFERENCE_BAR = {"t": 3.0, "dsr": 0.95, "dd": 20.0}
CANDIDATE_BAR = {"t": 2.5, "dsr": 0.95, "dd": 20.0}

# Блоки прогонов: (каталог, файл с результатами, порядок итерации для
# восстановления имени каталога). Имена каталогов = {family}-{risk}-{index},
# где index растёт в порядке цикла. Порядок цикла задан в исходных скриптах.
BLOCKS: list[dict[str, Any]] = [
    {
        "name": "scan-10k",
        "dir": FOUNDER / "scan-10k",
        "results": FOUNDER / "scan-10k" / "scan-results.json",
        "order": ["family", "symbol", "risk"],
        "risks": ["raw", "vol10", "vol12dd820"],
        "families": None,          # из archetype_grid.VARIANTS
        "symbols": None,           # TOP_SYMBOLS из scan_10k.py
    },
    {
        "name": "freqtrade-scan",
        "dir": FOUNDER / "freqtrade-scan",
        "results": FOUNDER / "freqtrade-scan" / "scan-results.json",
        "order": ["family", "symbol", "risk"],
        "risks": ["raw", "vol10"],
        "families": None,          # из freqtrade_engines.RULES
        "symbols": None,           # TOP_SYMBOLS из freqtrade_scan.py
    },
]

TOP_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
    "XRPUSDT", "LTCUSDT", "DOGEUSDT", "LINKUSDT", "DOTUSDT",
    "TRXUSDT", "BCHUSDT", "ATOMUSDT", "ETCUSDT", "XLMUSDT",
    "AVAXUSDT", "DASHUSDT", "NEOUSDT", "ZECUSDT", "QTUMUSDT",
    "ALGOUSDT", "VETUSDT", "HOTUSDT", "ZILUSDT", "MANAUSDT",
    "ENJUSDT", "IOTXUSDT", "CFXUSDT", "ONTUSDT", "THETAUSDT",
]


def _returns(run_dir: Path) -> pd.Series:
    path = run_dir / "artifacts" / "equity.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
    if "ret" in frame.columns:
        return frame["ret"].dropna().astype(float)
    equity = frame.set_index("timestamp")["equity"].astype(float)
    return equity.pct_change().dropna()


def _metrics(returns: pd.Series) -> dict[str, float | int | None]:
    clean = pd.Series(returns).dropna()
    n = len(clean)
    if n < 2:
        return {"n_obs": n, "sharpe_per_obs": None, "t_stat": None,
                "skew": None, "kurtosis": None, "max_dd_pct": None}
    values = clean.to_numpy(dtype=float)
    std = float(values.std(ddof=1))
    sharpe = float(values.mean() / std) if std > 0 else None
    t_stat = float(values.mean() / std * math.sqrt(n)) if std > 0 else None
    centred = (values - values.mean()) / std if std > 0 else values * 0
    skew = float(np.mean(centred**3))
    kurtosis = float(np.mean(centred**4))
    equity = (1.0 + clean).cumprod()
    dd = float((equity / equity.cummax() - 1.0).min())
    return {"n_obs": n, "sharpe_per_obs": sharpe, "t_stat": t_stat,
            "skew": skew, "kurtosis": kurtosis, "max_dd_pct": abs(dd) * 100.0}


def _scan10k_families() -> list[str]:
    from archetype_grid import VARIANTS
    return list(VARIANTS.keys())


def _freqtrade_families() -> list[str]:
    from freqtrade_engines import RULES
    return list(RULES.keys())


def _reconstruct_dirs(block: dict[str, Any], n_rows: int) -> list[Path]:
    """Восстанавливает порядок каталогов {family}-{risk}-{index}."""
    families = block["families"]
    symbols = block["symbols"]
    risks = block["risks"]
    dirs: list[Path] = []
    index = 0
    for family in families:
        params_list = block.get("params_list", {}).get(family, [None])
        for _params in params_list:
            for symbol in symbols:
                for risk in risks:
                    index += 1
                    dirs.append(block["dir"] / f"{family}-{risk}-{index}")
    if len(dirs) != n_rows:
        raise SystemExit(f"{block['name']}: {len(dirs)} dirs vs {n_rows} rows")
    return dirs


def collect() -> list[dict[str, Any]]:
    """Собирает метрики по всем прогонам всех блоков."""
    rows: list[dict[str, Any]] = []

    # --- scan-10k -------------------------------------------------------
    block = BLOCKS[0]
    data = json.loads(block["results"].read_text(encoding="utf-8"))["results"]
    variants = _scan10k_families()
    from archetype_grid import VARIANTS
    block["families"] = variants
    block["symbols"] = TOP_SYMBOLS
    block["params_list"] = {fam: VARIANTS[fam] for fam in variants}
    dirs = _reconstruct_dirs(block, len(data))
    for row, run_dir in zip(data, dirs):
        if row.get("status") != "OK":
            continue
        m = _metrics(_returns(run_dir))
        if m["n_obs"] < MIN_OBS or m["sharpe_per_obs"] is None:
            continue
        rows.append({
            "block": "scan-10k", "name": run_dir.name,
            "family": row.get("family"), "risk": row.get("risk"),
            "symbol": row.get("symbol"), **m,
        })
    print(f"scan-10k: {len(rows)} прогонов собрано", flush=True)

    # --- freqtrade-scan -------------------------------------------------
    before = len(rows)
    block = BLOCKS[1]
    data = json.loads(block["results"].read_text(encoding="utf-8"))["results"]
    rules = _freqtrade_families()
    block["families"] = rules
    block["symbols"] = TOP_SYMBOLS
    block["params_list"] = {rule: [None] for rule in rules}
    dirs = _reconstruct_dirs(block, len(data))
    for row, run_dir in zip(data, dirs):
        if row.get("status") != "OK":
            continue
        m = _metrics(_returns(run_dir))
        if m["n_obs"] < MIN_OBS or m["sharpe_per_obs"] is None:
            continue
        rows.append({
            "block": "freqtrade-scan", "name": run_dir.name,
            "family": row.get("family"), "risk": row.get("risk"),
            "symbol": row.get("symbol"), **m,
        })
    print(f"freqtrade-scan: {len(rows) - before} прогонов собрано", flush=True)

    # --- archetype-scan и risk-overlay ----------------------------------
    # У них нет результатов в scan-results.json с тем же индексом, поэтому
    # берём equity напрямую из каждого каталога и имя = имя каталога.
    for block_name in ("archetype-scan", "risk-overlay"):
        base = FOUNDER / block_name
        if not base.exists():
            continue
        before = len(rows)
        for run_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            if not (run_dir / "artifacts" / "equity.csv").exists():
                continue
            m = _metrics(_returns(run_dir))
            if m["n_obs"] < MIN_OBS or m["sharpe_per_obs"] is None:
                continue
            parts = run_dir.name.rsplit("-", 1)
            rows.append({
                "block": block_name, "name": run_dir.name,
                "family": parts[0] if parts else run_dir.name,
                "risk": "", "symbol": "", **m,
            })
        print(f"{block_name}: {len(rows) - before} прогонов собрано", flush=True)

    return rows


def main() -> None:
    rows = collect()
    if not rows:
        raise SystemExit("no runs collected")

    sharpes = [r["sharpe_per_obs"] for r in rows]
    n_trials = len(rows)
    trial_std = float(pd.Series(sharpes).std(ddof=1))
    expected_fp = n_trials * 0.05

    print(f"\nпул испытаний: {n_trials} | trial_sharpe_std (периодическая шкала): {trial_std:.5f}")
    print(f"ожидаемо ложных при 5%: {expected_fp:.1f}")

    for row in rows:
        try:
            result = deflated_sharpe_ratio(
                observed_sharpe=row["sharpe_per_obs"],
                n_trials=n_trials,
                n_observations=row["n_obs"],
                trial_sharpe_std=trial_std,
                skew=row["skew"],
                kurtosis=row["kurtosis"],
            )
            row["dsr"] = float(getattr(result, "deflated_sharpe_ratio", 0.0)) if result else None
        except (ValueError, ZeroDivisionError):
            row["dsr"] = None
        t = row["t_stat"]
        dd = row["max_dd_pct"]
        row["gate_reference"] = bool(
            t is not None and t >= REFERENCE_BAR["t"]
            and row["dsr"] is not None and row["dsr"] >= REFERENCE_BAR["dsr"]
            and dd is not None and dd <= REFERENCE_BAR["dd"]
        )
        row["gate_candidate"] = bool(
            t is not None and t >= CANDIDATE_BAR["t"]
            and row["dsr"] is not None and row["dsr"] >= CANDIDATE_BAR["dsr"]
            and dd is not None and dd <= CANDIDATE_BAR["dd"]
        )

    reference = sorted([r for r in rows if r["gate_reference"]], key=lambda r: -(r["sharpe_per_obs"] or 0))
    candidates = sorted([r for r in rows if r["gate_candidate"]], key=lambda r: -(r["sharpe_per_obs"] or 0))

    # Отдельно: проверяем конкретные строки, которые фигурировали в отчётах.
    spotlight = [
        r for r in rows
        if r["family"] in {"roc10", "roc30", "bb_ride"}
        and r["symbol"] in {"AVAXUSDT", "BTCUSDT", "SOLUSDT"}
    ]

    verdict = {
        "date": "2026-10-25",
        "scale": "per-observation Sharpe (mean/std), без sqrt(365) — как требует multipletesting.py",
        "n_trials_pooled": n_trials,
        "trial_sharpe_std": round(trial_std, 6),
        "expected_false_positives_5pct": round(expected_fp, 1),
        "reference_bar": REFERENCE_BAR,
        "candidate_bar": CANDIDATE_BAR,
        "n_reference": len(reference),
        "n_candidate": len(candidates),
        "reference_edges": reference[:50],
        "candidates_top50": candidates[:50],
        "spotlight_roc10": spotlight,
        "all_rows": rows,
        "limitation": "DSR предполагает независимость испытаний; стратегии на одной паре коррелированы. "
                     " skew/kurtosis — по реальному ряду. Это пересчёт уже опубликованных чисел, "
                     " а НЕ новый чистый тест: пул уже виден.",
    }
    OUT.write_text(json.dumps(verdict, indent=1, ensure_ascii=False, default=str), encoding="utf-8")

    print("\n=== ЧЕСТНЫЙ DSR-ПЕРЕСЧЁТ (периодическая шкала) ===")
    print(f"REFERENCE (t>=3 + DSR>=0.95 + |DD|<=20%): {len(reference)}")
    for r in reference[:20]:
        print(f"  {r['block']:15s} {r['name']:28s} {r['symbol']:10s} "
              f"t={r['t_stat']:.3f} DSR={r['dsr']:.4f} DD={r['max_dd_pct']:.1f}% "
              f"sharpe/obs={r['sharpe_per_obs']:.5f}")
    print(f"CANDIDATE (t>=2.5 + DSR>=0.95 + |DD|<=20%): {len(candidates)}")
    for r in candidates[:20]:
        print(f"  {r['block']:15s} {r['name']:28s} {r['symbol']:10s} "
              f"t={r['t_stat']:.3f} DSR={r['dsr']:.4f} DD={r['max_dd_pct']:.1f}%")

    print("\n=== SPOTLIGHT: строки из прежних отчётов ===")
    for r in sorted(spotlight, key=lambda x: -(x["sharpe_per_obs"] or 0))[:12]:
        print(f"  {r['name']:30s} {r['symbol']:10s} risk={r['risk']:8s} "
              f"t={r['t_stat']:.3f} DSR={r['dsr']} DD={r['max_dd_pct']:.1f}% "
              f"REF={r['gate_reference']} CAND={r['gate_candidate']}")
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
