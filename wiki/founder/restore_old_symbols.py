"""Восстановление пары и режима риска для старых прогонов.

Проблема: при упаковке старых блоков в metrics.jsonl попали только метрики -
без пары и без режима риска. А имя прогона вида "roc10-raw-811" содержит
номер индекса, а не пару, поэтому в панели колонки ПАРА и РИСК были пустыми.

Как восстанавливается: номер в имени - это порядковый номер прогона в
переборе вида "for rule: for symbol: for risk". Перебор детерминированный
(списки RULES и TOP_SYMBOLS в коде сканера), значит индекс однозначно
разворачивается обратно в (правило, пара, риск).

Порядок циклов в freqtrade_scan.py:
    for rule in RULES:
        for symbol in TOP_SYMBOLS:
            for risk_name, engine in _risk_engines(rule):
                index += 1
    -> run_dir = f"{rule}-{risk_name}-{index}"

Для scan_10k.py и archetype_scan.py порядок свой - он читается из их кода.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(FOUNDER))


def _freqtrade_map() -> dict[int, tuple[str, str, str]]:
    """{index: (rule, symbol, risk)} для блока freqtrade-scan."""
    import freqtrade_scan as fs

    out: dict[int, tuple[str, str, str]] = {}
    index = 0
    for rule in fs.RULES:
        for symbol in fs.TOP_SYMBOLS:
            for risk_name, _engine in fs._risk_engines(rule):
                index += 1
                out[index] = (rule, symbol, risk_name)
    return out


def _scan10k_map() -> dict[int, tuple[str, str, str]]:
    """{index: (family, symbol, risk)} для блока scan-10k.

    Порядок из scan_10k.main():
        variants = [(family, params) for family, plist in VARIANTS.items() for params in plist]
        for family, params in variants:
            for symbol in TOP_SYMBOLS:
                for risk_name, engine in _risk_engines(family, params):
    """
    import scan_10k as s10

    variants = [(family, params)
                for family, plist in s10.VARIANTS.items() for params in plist]
    out: dict[int, tuple[str, str, str]] = {}
    index = 0
    for family, params in variants:
        for symbol in s10.TOP_SYMBOLS:
            for risk_name, _engine in s10._risk_engines(family, params):
                index += 1
                out[index] = (family, symbol, risk_name)
    return out


def _archetype_map() -> dict[int, tuple[str, str, str]]:
    """{index: (family, symbol, risk)} для блока archetype-scan.

    Порядок из archetype_scan.main():
        variants = [(family, "multi", params, None) for family, plist in VARIANTS.items() for params in plist]
        for family, _tag, params, _ in variants:
            for symbol in TOP_SYMBOLS:
                run_index += 1
    Имя каталога здесь "{family}-{run_index}" - без режима риска.
    """
    import archetype_scan as a_s

    variants = [(family, "multi", params, None)
                for family, plist in a_s.VARIANTS.items() for params in plist]
    out: dict[int, tuple[str, str, str]] = {}
    index = 0
    for family, _tag, _params, _ in variants:
        for symbol in a_s.TOP_SYMBOLS:
            index += 1
            out[index] = (family, symbol, "raw")
    return out


def _risk_overlay_map() -> dict[int, tuple[str, str, str]]:
    """risk-overlay: пара и режим риска прямо в имени каталога.

    Имя: "{family}-{SYMBOL}-{risk}-{index}", например
    "MARegimeFilter-SOLUSDT-ddthrottle-20". Список overlays собирается в
    рантайме из выживших после g4, поэтому карта строится по самим именам.
    """
    return {}


def _parse_overlay_name(name: str) -> tuple[str, str, str] | None:
    """'MARegimeFilter-SOLUSDT-ddthrottle-20' -> ('MARegimeFilter','SOLUSDT','ddthrottle')."""
    parts = name.split("-")
    if len(parts) < 3:
        return None
    symbol = parts[1]
    if not symbol.endswith("USDT"):
        return None
    risk = parts[2]
    if risk.startswith("ddthrottle"):
        risk = "ddthrottle"
    return parts[0], symbol, risk


BUILDERS = {
    "freqtrade-scan": _freqtrade_map,
    "scan-10k": _scan10k_map,
    "archetype-scan": _archetype_map,
    "risk-overlay": _risk_overlay_map,
}


def build_lookup(block: str) -> dict[int, tuple[str, str, str]]:
    builder = BUILDERS.get(block)
    if builder is None:
        return {}
    try:
        return builder()
    except Exception as exc:  # noqa: BLE001 — блок может не импортироваться
        print(f"  {block}: не удалось построить карту ({exc})")
        return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics",
                        default=str(FOUNDER / "old-returns" / "metrics.jsonl"))
    parser.add_argument("--out",
                        default=str(FOUNDER / "old-returns" / "symbols.json"))
    args = parser.parse_args()

    metrics_path = Path(args.metrics)
    rows = [json.loads(line) for line in metrics_path.open(encoding="utf-8")
            if line.strip()]

    by_block: dict[str, list[dict]] = {}
    for row in rows:
        by_block.setdefault(row.get("block", ""), []).append(row)

    result: dict[str, dict] = {}
    total = 0
    for block, block_rows in by_block.items():
        lookup = build_lookup(block)
        if not lookup and block == "risk-overlay":
            # У risk-overlay пара и риск прямо в имени каталога.
            resolved = 0
            for row in block_rows:
                parsed = _parse_overlay_name(row.get("name", ""))
                if parsed is None:
                    continue
                row["rule"], row["symbol"], row["risk"] = parsed
                resolved += 1
            result[block] = {row["name"]: {
                "rule": row.get("rule"), "symbol": row.get("symbol"),
                "risk": row.get("risk")} for row in block_rows}
            total += resolved
            print(f"{block}: восстановлено {resolved} из {len(block_rows)} (разбор имени)")
            sample = next(iter(result[block].items()))
            print(f"  пример: {sample[0]} -> {sample[1]}")
            continue
        if not lookup:
            print(f"{block}: карта недоступна, имена не разобраны")
            continue
        resolved = 0
        for row in block_rows:
            match = re.match(r"^(.*)-(\d+)$", row.get("name", ""))
            if not match:
                continue
            index = int(match.group(2))
            entry = lookup.get(index)
            if not entry:
                continue
            rule, symbol, risk = entry
            row["rule"] = rule
            row["symbol"] = symbol
            row["risk"] = risk
            resolved += 1
        result[block] = {row["name"]: {
            "rule": row.get("rule"), "symbol": row.get("symbol"),
            "risk": row.get("risk")} for row in block_rows}
        total += resolved
        print(f"{block}: восстановлено {resolved} из {len(block_rows)}")
        sample = next(iter(result[block].items()))
        print(f"  пример: {sample[0]} -> {sample[1]}")

    Path(args.out).write_text(json.dumps(result, indent=1, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwritten: {args.out} (всего {total})")


if __name__ == "__main__":
    main()
