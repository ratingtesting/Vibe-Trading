"""Jev как судья кандидатов: вероятности, а не только вердикт.

ЗАЧЕМ (владелец, 25.10.26)
«Всех 13 и новых кандидатов, если есть + с копилкой надо прогнать по Джеву,
возможно он как судья лучше укажет вероятности.»

Jev здесь — НЕ замена статистическому гейту. DSR и t решают, проходит ли
строка бар; Jev даёт ВТОРОЕ, независимое мнение с РАСПРЕДЕЛЕНИЕМ
ВЕРОЯТНОСТЕЙ по вариантам («этот кандидат / этот другой / ни один»), что
обычный PASS/FAIL не даёт. Именно поэтому его вывод помечается как
мнение, а не как доказательство.

ЧТО ПОДАЁТСЯ СУДЬЕ
- state: факты по кандидату (годовая, t, DSR, просадка, число наблюдений,
  BTC-копилка) — без интерпретаций и без вывода.
- questions: один вопрос с вариантами и ЧЕСТНЫМИ опциями:
    better  — «первый кандидат лучше второго»
    worse   — «второй лучше первого»
    equal   — «сопоставимы»
  Jev возвращает choice + вероятности + confidence.

ЧТО ВЫХОДИТ
- Сводная таблица: кандидат, choice, вероятности, confidence, провайдер,
  стоимость.
- Честная оговорка: при n вариантов и такой-то confidence это МНЕНИЕ, а не
  статистический тест; и оно не заменяет гейт.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
SCAN = FOUNDER / "scan5y"
RESULTS = SCAN / "scan-results.jsonl"
CANDIDATES = FOUNDER / "candidates-13-5y" / "kopilka-13-5y.json"
OUT = FOUNDER / "jev-judgement.json"

API = "http://127.0.0.1:8899/jev/judge"

QUESTION_ID = "which_candidate_is_better"


def _post(payload: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        API, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _state_text(row: dict[str, Any]) -> str:
    """Факты о кандидате — без выводов, чтобы судья не подражал нам."""
    lines = [
        "Кандидат A (первый):",
        f"- семейство стратегий: {row['a']['family']}",
        f"- торговая пара: {row['a']['symbol']}",
        f"- риск-режим: {row['a']['risk']}",
        f"- годовая доходность: {row['a']['annual_pct']:.2f}%",
        f"- t-статистика: {row['a']['t_stat']:.3f}",
        f"- дефлятированный Sharpe (DSR): {row['a'].get('dsr', 0.0):.4f}",
        f"- максимальная просадка: {row['a']['max_dd_pct']:.2f}%",
        f"- число наблюдений: {row['a']['n_obs']}",
    ]
    if row["a"].get("kopilka"):
        k = row["a"]["kopilka"]
        lines += [
            f"- с BTC-копилкой годовая: {k['annual_pct']:.2f}%",
            f"- накоплено BTC: {k['final_btc_units']:.6f} шт (${k['final_btc_value']:.2f})",
            f"- доля BTC в счёте: {k['btc_share_pct']:.1f}%",
        ]
    lines += [
        "",
        "Кандидат B (второй):",
        f"- семейство стратегий: {row['b']['family']}",
        f"- торговая пара: {row['b']['symbol']}",
        f"- риск-режим: {row['b']['risk']}",
        f"- годовая доходность: {row['b']['annual_pct']:.2f}%",
        f"- t-статистика: {row['b']['t_stat']:.3f}",
        f"- дефлятированный Sharpe (DSR): {row['b'].get('dsr', 0.0):.4f}",
        f"- максимальная просадка: {row['b']['max_dd_pct']:.2f}%",
        f"- число наблюдений: {row['b']['n_obs']}",
    ]
    if row["b"].get("kopilka"):
        k = row["b"]["kopilka"]
        lines += [
            f"- с BTC-копилкой годовая: {k['annual_pct']:.2f}%",
            f"- накоплено BTC: {k['final_btc_units']:.6f} шт (${k['final_btc_value']:.2f})",
            f"- доля BTC в счёте: {k['btc_share_pct']:.1f}%",
        ]
    lines += [
        "",
        "Окно наблюдений у обоих: 5 лет, 2021-10-20..2026-10-19, дневные бары.",
        "Все кандидаты отобраны из одного и того же пула прогонов.",
    ]
    return "\n".join(lines)


def _questions() -> dict[str, dict[str, Any]]:
    """Контракт Jev: type=choice, instructions, criteria (словарь опций).

    Именно эта форма описана в agent/jev_module/README.md: ключ "type"
    обязателен (choice | score | noul), опции задаются словарём criteria.
    Без "type" провайдер отвечает HTTP 400 и оба попадают в карантин.
    """
    return {
        QUESTION_ID: {
            "type": "choice",
            "instructions": (
                "Какой из двух кандидатов лучше как ТОРГОВЫЙ кандидат? "
                "Учитывай доходность, статистическую значимость (t и DSR) и "
                "просадку. Отвечай только по приведённым числам."
            ),
            "criteria": {
                "a_better": "кандидат A лучше кандидата B",
                "b_better": "кандидат B лучше кандидата A",
                "equal": "оба кандидата сопоставимы",
            },
        }
    }


def _load_candidates() -> list[dict[str, Any]]:
    """13 кандидатов с копилкой + лучшие из 5-летнего скана."""
    out: list[dict[str, Any]] = []
    if CANDIDATES.exists():
        payload = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        for row in payload.get("rows", []):
            if row["kopilka"].get("status") != "OK":
                continue
            out.append({
                "source": "13-кандидаты",
                "id": row["id"],
                "family": row["family"],
                "symbol": row["symbol"],
                "risk": row["risk"],
                "annual_pct": row["kopilka"]["annual_pct"],
                "t_stat": row["base"]["t_stat"] or 0.0,
                "max_dd_pct": row["kopilka"]["max_dd_pct"],
                "n_obs": row["base"]["n_obs"],
                "kopilka": row["kopilka"],
            })
    if RESULTS.exists():
        rows = []
        with RESULTS.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        ok = [r for r in rows if r.get("status") == "OK"]
        ok.sort(key=lambda r: -(r.get("t_stat") or -99))
        for r in ok[:10]:
            out.append({
                "source": "скан-5лет",
                "id": f"{r['family']}/{r['symbol']}/{r['risk']}",
                "family": r["family"],
                "symbol": r["symbol"],
                "risk": r["risk"],
                "annual_pct": r["annual_pct"],
                "t_stat": r["t_stat"] or 0.0,
                "max_dd_pct": r["max_dd_pct"],
                "n_obs": r["n_obs"],
                "kopilka": None,
            })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=8, help="сколько пар судить")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    candidates = _load_candidates()
    if len(candidates) < 2:
        raise SystemExit("нужно минимум 2 кандидата")
    print(f"кандидатов к суду: {len(candidates)}")

    # Пары: каждый кандидат из «сильного» списка против следующего по t,
    # чтобы судья сравнивал близких, а не лучшего с худшим.
    judged: list[dict[str, Any]] = []
    pairs = min(args.pairs, len(candidates) - 1)
    for i in range(pairs):
        pair = {"a": candidates[i], "b": candidates[i + 1]}
        payload = {
            "state": _state_text(pair),
            "questions": _questions(),
            "timeout": args.timeout,
        }
        started = time.time()
        try:
            response = _post(payload, timeout=args.timeout + 15)
            judged.append({
                "a": pair["a"]["id"], "b": pair["b"]["id"],
                "a_source": pair["a"]["source"], "b_source": pair["b"]["source"],
                "choice": response.get("choice"),
                "probabilities": response.get("probabilities"),
                "confidence": response.get("confidence"),
                "provider": response.get("provider_name"),
                "model": response.get("model"),
                "cost_usd": response.get("cost_usd"),
                "latency_ms": response.get("latency_ms"),
                "elapsed_s": round(time.time() - started, 2),
            })
            print(f"  пара {i+1}: {response.get('choice')} "
                  f"conf={response.get('confidence')} "
                  f"({response.get('provider_name')})")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            judged.append({
                "a": pair["a"]["id"], "b": pair["b"]["id"],
                "error": str(exc)[:200],
                "elapsed_s": round(time.time() - started, 2),
            })
            print(f"  пара {i+1}: ОШИБКА {exc}")

    out = {
        "date": "2026-10-25",
        "role": "Второе мнение с распределением вероятностей. НЕ заменяет "
                "статистический гейт (t>=3, DSR>=0.95, |DD|<=20%) и не "
                "является доказательством прибыльности.",
        "n_candidates_loaded": len(candidates),
        "n_pairs": len(judged),
        "judgements": judged,
    }
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nwritten: {OUT}")


if __name__ == "__main__":
    main()
