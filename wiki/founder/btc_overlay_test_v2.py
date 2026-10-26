"""BTC-конвертация: сравнение портфеля из 13 стратегий БЕЗ и С дополнением Петра.

ПРЕДРЕГИСТРАЦИЯ: preregistration_btc_overlay.py (R1-R4, объявлены до прогона).

КОРРЕКТНАЯ симуляция с явными юнитами (v2, заменяет сломанную v1):
  - активы: портфельный индекс (13 стратегий, risk-parity, vol-target 12%)
    и BTC (цена из панели); кэш 10% на старте.
  - R1-профит: когда портфельная часть выросла на 30%+ от последней фиксации —
    продать юниты портфеля на 60% прироста и купить BTC.
  - R2/R3: пробой 50-дневного максимума BTC — продать транш BTC (10%, 10%, 5%
    от BTC-части) и купить портфель; если пробоя нет — транши остаются в BTC.
  - Коридор: ежемесячно, если доля BTC в счёте вышла из 20-30% — ребаланс к
    25% (15% BTC + 10% кэш). Издержка 10 bps на каждый перелив.

Выход: таблица сравнения БЕЗ/С overlay + накопленный BTC.
"""

from __future__ import annotations

import json
import pickle  # наш собственный файл, не недоверенный ввод
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "wiki" / "founder"))
from risk_parity_portfolio import _collect, _simulate, dev_weights_of, vol_targeted  # noqa: E402

OUT = REPO / "wiki" / "founder" / "btc-overlay-verdict.json"
COST = 0.001  # 10 bps на перелив


def _btc_prices() -> pd.Series:
    with open(REPO / "data" / "founder-crypto-panel.pkl", "rb") as fh:
        panel = pickle.load(fh)
    return panel["close"]["BTCUSDT"].dropna()


def stats(r: pd.Series) -> dict[str, float]:
    r = r.dropna()
    eq = (1 + r).cumprod()
    dd = float((eq / eq.cummax() - 1).min()) * 100
    ann = float((1 + r).prod() ** (365 / len(r)) - 1) * 100
    t = float(r.mean() / r.std(ddof=1) * (len(r) ** 0.5)) if r.std(ddof=1) > 0 else 0.0
    return {"annual_pct": ann, "t_stat": t, "max_dd_pct": dd, "days": len(r)}


def run_overlay(port: pd.Series, btc: pd.Series) -> dict[str, object]:
    idx = port.index.intersection(btc.index)
    p_ret = port.reindex(idx).fillna(0.0)
    b_price = btc.reindex(idx).ffill()
    p_index = (1 + p_ret).cumprod()

    cash = 0.10
    units_port = 0.90 / float(p_index.iloc[0])
    units_btc = 0.0
    last_lock = 0.90
    tranche = 0
    peak50 = b_price.iloc[:50].max()
    month = None
    daily_value = []

    for date in idx:
        pv = units_port * float(p_index.loc[date])
        bv = units_btc * float(b_price.loc[date])
        value = pv + bv + cash

        # R1-профит: прирост портфельной части >= 30% от последней фиксации
        if pv >= last_lock * 1.30:
            gain = pv - last_lock
            move = 0.60 * gain * (1 - COST)
            if move > 0 and float(b_price.loc[date]) > 0:
                units_port -= move / float(p_index.loc[date])
                units_btc += move / float(b_price.loc[date])
                last_lock = pv - move

        # R2/R3: пробой 50d-max BTC -> транши из BTC в портфель
        price = float(b_price.loc[date])
        if price > peak50 and tranche < 3:
            frac = (0.10, 0.10, 0.05)[tranche]
            sell = units_btc * frac
            proceeds = sell * price * (1 - COST)
            units_btc -= sell
            units_port += proceeds / float(p_index.loc[date])
            tranche += 1
        if price > peak50:
            peak50 = price

        # коридор: ежемесячно. Интерпретация идеи владельца: BTC КОПИТСЯ —
        # продаём BTC только по траншам R2/R3; коридор лишь докупает BTC из
        # портфеля, если доля упала ниже 20%.
        if month != date.month:
            month = date.month
            pv2 = units_port * float(p_index.loc[date])
            bv2 = units_btc * float(b_price.loc[date])
            v = pv2 + bv2 + cash
            share = bv2 / v if v > 0 else 0
            if share < 0.20:
                target_btc = 0.15 * v
                diff = target_btc - bv2
                if diff > 0:  # докупить BTC за счёт портфеля
                    sell_port = min(pv2, abs(diff) * (1 + COST))
                    cost = sell_port * COST
                    units_port -= sell_port / float(p_index.loc[date])
                    units_btc += (sell_port - cost) / float(b_price.loc[date])
                    last_lock = min(last_lock, units_port * float(p_index.loc[date]))

        daily_value.append(units_port * float(p_index.loc[date]) + units_btc * float(b_price.loc[date]) + cash)

    eq = pd.Series(daily_value, index=idx)
    r = eq.pct_change().dropna()
    out = stats(r)
    out["btc_accumulated"] = float(units_btc)
    out["final_value"] = float(eq.iloc[-1])
    out["final_portfolio_value"] = float(units_port * float(p_index.iloc[-1]))
    out["final_cash"] = float(cash)
    return out


def main() -> None:
    series = _collect()
    returns = pd.DataFrame(series).dropna()
    w = dev_weights_of(returns)
    port = _simulate(returns, pd.Series(w), returns.index)
    vt = vol_targeted(port, 0.12)
    btc = _btc_prices()

    base = stats(vt)
    base.update({"btc_accumulated": 0.0})
    over = run_overlay(vt, btc)

    verdict = {
        "date": "2026-10-24",
        "prereg": "preregistration_btc_overlay.py (R1-R4, объявлено до прогона)",
        "baseline": base,
        "with_overlay": over,
        "btc_price_start": float(btc.iloc[0]),
        "btc_price_end": float(btc.iloc[-1]),
        "acceptance": "принять если overlay улучшает доходность ИЛИ уменьшает DD без t<2.5",
        "honest_note": "10 bps на перелив, транши R2/R3, коридор 20-30% ежемесячно",
    }
    OUT.write_text(json.dumps(verdict, indent=1, ensure_ascii=False), encoding="utf-8")
    print("=== БАЗА (100% портфель vol-target 12%) ===")
    print(f"  {base['annual_pct']:+.2f}%/год t={base['t_stat']:.3f} DD={base['max_dd_pct']:.1f}% BTC=0")
    print("=== С BTC-КОНВЕРТАЦИЕЙ (R1-R4) ===")
    print(f"  {over['annual_pct']:+.2f}%/год t={over['t_stat']:.3f} DD={over['max_dd_pct']:.1f}%")
    # счёт в симуляции стартует с $1; пересчёт юнитов на старт $100 для читаемости
    print(f"  BTC накоплено (при старте со $100): {over['btc_accumulated'] * 100:.6f} BTC")
    print(f"  доля BTC в счёте на конец: {over['btc_accumulated'] * verdict['btc_price_end'] / over['final_value'] * 100:.1f}%")
    print(f"  финальная стоимость счёта (старт $1.00): ${over['final_value']:,.2f} (= ${over['final_value'] * 100:,.0f} при старте $100)")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
