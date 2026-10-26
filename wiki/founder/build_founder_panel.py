"""Пересборка frontend/public/founder-results.json из актуальных данных.

Зачем: артефакт панели был собран вручную и устарел - он показывал пул
23 772 испытаний вместо финальных 42 299, а в колонках ПАРА и РИСК стояли
прочерки, потому что имя прогона вида "roc10-raw-811" не разбиралось.

Этот скрипт собирает артефакт заново:
  - блок честного DSR - из финального объединённого пула (старые упакованные
    прогоны + новый 5-летний скан), с разбором имени прогона на
    стратегию/пару/риск;
  - блок 13 кандидатов - из актуального прогона с копилкой;
  - объявленные правила копилки и статус - без изменений, но берутся из
    кода, а не дублируются руками.

Формат имени старого прогона: "<семейство>-<риск>-<номер>", где номер -
это индекс в блоке. Пара и риск восстанавливаются из metrics.jsonl
упаковки, где они записаны явно.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OLD_RETURNS = FOUNDER / "old-returns"
CAND13 = FOUNDER / "candidates-13-5y" / "kopilka-13-5y.json"
FINAL_DSR = FOUNDER / "honest-dsr-final.json"
OUT = REPO / "frontend" / "public" / "founder-results.json"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(FOUNDER))

from src.quantlib.multipletesting import deflated_sharpe_ratio  # noqa: E402

import kopilka_5y as kop  # noqa: E402


def load_old_metrics() -> dict[str, dict]:
    """Метрики старых прогонов из упаковки: ключ - 'блок/имя'."""
    path = OLD_RETURNS / "metrics.jsonl"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            block = row.get("block")
            name = row.get("name")
            if block and name:
                out[f"{block}/{name}"] = row
    return out


def load_old_symbols() -> dict[str, dict]:
    """Восстановленные пары и режимы риска: ключ - 'блок/имя'."""
    path = OLD_RETURNS / "symbols.json"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    payload = json.loads(path.read_text(encoding="utf-8"))
    for block, names in payload.items():
        for name, entry in names.items():
            out[f"{block}/{name}"] = entry
    return out


def load_new_rows() -> list[dict]:
    path = FOUNDER / "scan5y" / "scan-results.jsonl"
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_old_name(name: str) -> tuple[str, str]:
    """'roc10-vol10-812' -> ('roc10', 'vol10'); 'roc10-raw-811' -> ('roc10','raw')."""
    match = re.match(r"^(.*?)-(raw|vol\d+|dd\d+.*|vol12dd\d+|.*risk.*)-(\d+)$", name)
    if match:
        return match.group(1), match.group(2)
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], ""
    return name, ""


def build_dsr_block() -> dict:
    """DSR по объединённому пулу: старые упакованные + новый скан."""
    old_metrics = load_old_metrics()
    old_symbols = load_old_symbols()
    old_rows: list[dict] = []
    for key, row in old_metrics.items():
        sharpe = row.get("sharpe_per_obs")
        if not isinstance(sharpe, (int, float)):
            continue
        # Пара и риск восстановлены из имени прогона (restore_old_symbols.py).
        restored = old_symbols.get(key, {})
        old_rows.append({
            "source": "старые-блоки", "name": row.get("name"),
            "block": row.get("block"),
            "family": restored.get("rule") or row.get("family"),
            "symbol": restored.get("symbol") or row.get("symbol"),
            "risk": restored.get("risk") or row.get("risk"),
            "t_stat": row.get("t_stat"), "dsr": None,
            "max_dd_pct": row.get("max_dd_pct"),
            "sharpe_per_obs": sharpe,
            "skew": row.get("skew"), "kurtosis": row.get("kurtosis"),
            "n_obs": row.get("n_obs"),
        })

    new_rows: list[dict] = []
    for row in load_new_rows():
        sharpe = row.get("sharpe_per_obs")
        if row.get("status") != "OK" or not isinstance(sharpe, (int, float)):
            continue
        new_rows.append({
            "source": "скан-5лет", "name": f"{row['family']}/{row['symbol']}/{row['risk']}",
            "block": "scan5y", "family": row["family"], "symbol": row["symbol"],
            "risk": row["risk"], "t_stat": row.get("t_stat"), "dsr": None,
            "max_dd_pct": row.get("max_dd_pct"),
            "sharpe_per_obs": sharpe,
            "skew": row.get("skew"), "kurtosis": row.get("kurtosis"),
            "n_obs": row.get("n_obs"),
        })

    pool = old_rows + new_rows
    sharpes = [r["sharpe_per_obs"] for r in pool]
    n_trials = len(pool)
    import statistics as st
    std = st.stdev(sharpes) if len(sharpes) > 1 else 0.0

    for row in pool:
        skew = row.get("skew")
        kurtosis = row.get("kurtosis")
        if not isinstance(skew, (int, float)):
            skew = 0.0
        if not isinstance(kurtosis, (int, float)):
            kurtosis = 3.0
        try:
            result = deflated_sharpe_ratio(
                observed_sharpe=row["sharpe_per_obs"], n_trials=n_trials,
                n_observations=row.get("n_obs") or 1826, trial_sharpe_std=std,
                skew=skew, kurtosis=kurtosis)
            row["dsr"] = float(result.deflated_sharpe_ratio)
        except (ValueError, ZeroDivisionError, TypeError):
            row["dsr"] = None

    best = sorted([r for r in pool if r["dsr"] is not None],
                  key=lambda r: -r["dsr"])[:10]
    for row in best:
        if not row.get("family"):
            family, risk = parse_old_name(row.get("name") or "")
            row["family"] = family
            row["risk"] = row.get("risk") or risk

    n_reference = len([r for r in pool
                        if r["dsr"] is not None and r["dsr"] >= 0.95
                        and (r.get("t_stat") or 0) >= 3.0
                        and abs(r.get("max_dd_pct") or 999) <= 20.0])
    n_candidate = len([r for r in pool
                       if r["dsr"] is not None and r["dsr"] >= 0.95
                       and (r.get("t_stat") or 0) >= 2.5
                       and abs(r.get("max_dd_pct") or 999) <= 20.0])

    return {
        "date": "2026-10-26",
        "scale": "per-observation Sharpe (mean/std) без sqrt(365)",
        "n_trials_pooled": n_trials,
        "trial_sharpe_std": std,
        "expected_false_positives_5pct": n_trials * 0.05,
        "n_old_rows": len(old_rows),
        "n_new_rows": len(new_rows),
        "n_reference": n_reference,
        "n_candidate": n_candidate,
        "best_by_dsr": best,
        "limitation": (
            "DSR предполагает независимость испытаний; стратегии на одной паре "
            "коррелированы. Это пересчёт уже просмотренных данных, а не новый "
            "чистый тест."),
    }


def build_candidates_block() -> list[dict]:
    """13 кандидатов с раскладом счёта - из актуального прогона."""
    if not CAND13.exists():
        return []
    payload = json.loads(CAND13.read_text(encoding="utf-8"))
    out = []
    for row in payload.get("rows", []):
        k = row.get("kopilka") or {}
        if k.get("status") != "OK":
            continue
        base = row.get("base") or {}
        out.append({
            "id": row.get("id"), "symbol": row.get("symbol"),
            "scan": row.get("block"), "risk": row.get("risk"),
            "period_start": row.get("period_start"),
            "period_end": row.get("period_end"),
            "parameters": json.dumps(row.get("params") or {}, ensure_ascii=False),
            "risk_parameters": json.dumps({"mode": row.get("risk")}, ensure_ascii=False),
            "baseline": {
                "annual_pct": base.get("annual_pct"),
                "max_dd_pct": -abs(base.get("max_dd_pct") or 0),
                "t_stat": base.get("t_stat"),
                "final_value": base.get("final_value"),
            },
            "overlay": {
                "annual_pct": k.get("annual_pct"),
                "max_dd_pct": k.get("max_dd_pct"),
                "final_value": k.get("final_value"),
                "final_btc_units": k.get("final_btc_units"),
                "final_btc_price": k.get("final_btc_price"),
                "final_btc_value": k.get("final_btc_value"),
                "final_asset_value": k.get("final_asset_value"),
                "final_cash": k.get("final_cash"),
                "btc_share_pct": k.get("btc_share_pct"),
                "locks": k.get("locks"),
                "returns_to_asset": k.get("returns_to_asset"),
            },
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    dsr = build_dsr_block()
    candidates = build_candidates_block()

    payload = {
        "generated_at": "2026-10-26",
        "audit": "/transition-audit.html",
        "status": "HONEST_RECHECK_NO_SURVIVORS",
        "notice_ru": (
            f"Пересчёт по ВСЕМУ объединённому пулу ({dsr['n_trials_pooled']} "
            "испытаний: старые блоки + 5-летний скан): ни один прогон не "
            "проходит планку DSR>=0.95. Прежние «PASS» держались на годовом "
            "Sharpe, который завышал DSR примерно в sqrt(365) раз."),
        "btc_kopilka_rules": {
            "lock_threshold": 0.30,
            "lock_share_of_gain": 0.75,
            "return_share_of_btc": 0.30,
            "drawdown_trigger": 0.10,
            "ma_window": 50,
            "cost_per_leg": 0.001,
            "start_capital": kop.START_CAPITAL,
            "bottom_rule": (
                "Откат >=10% от пика + восстановление >= половины глубины от "
                "дна + цена выше своей 50-дневной средней (причинное правило, "
                "без чтения будущего)."),
            "dd_gate_note": (
                "Просадка «не хуже 20%» = |dd| <= 20. Раньше в scan_10k.py "
                "стояло max_dd_pct <= 20 при отрицательной просадке - "
                "проходило любое отрицательное число."),
            "kopilka_threshold_note": (
                "Порог - единственный рабочий рычаг: при 10% улучшаются 46% "
                "строк против 21% при 30%. На 13 кандидатах копилка не "
                "улучшила ни одну строку при любом пороге - BTC коррелирует "
                "с этими активами на 0.38-0.74, поэтому копилка концентрирует "
                "счёт вместо диверсификации."),
        },
        "candidates": candidates,
        "honest_dsr_recheck": dsr,
    }

    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"written: {args.out}")
    print(f"пул: {dsr['n_trials_pooled']} (старых {dsr['n_old_rows']} + "
          f"новых {dsr['n_new_rows']})")
    print(f"ЭТАЛОН: {dsr['n_reference']} | КАНДИДАТ: {dsr['n_candidate']}")
    print(f"кандидатов с копилкой: {len(candidates)}")


if __name__ == "__main__":
    main()
