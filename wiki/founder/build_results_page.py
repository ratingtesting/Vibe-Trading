"""Founder results page: SVG equity chart + survivor tables, no external deps.

Writes wiki/founder/results-page.html so the founder can open it in the panel
(pickle): the risk-parity portfolio equity curve, the 13 G4+G5 survivors with
drawdown, the 18 combo candidates, and the Jev implementation pointer. Data
comes from the JSON artifacts the scans wrote; nothing is recomputed here.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FOUNDER = REPO / "wiki" / "founder"
OUT = FOUNDER / "results-page.html"


def _portfolio_equity() -> pd.Series:  # type: ignore[name-defined]
    """Rebuild the full-sample vol-targeted portfolio equity from the saved daily returns."""
    import sys
    sys.path.insert(0, str(FOUNDER))
    import numpy as np
    import pandas as pd
    from risk_parity_portfolio import _collect, _simulate, vol_targeted, dev_weights_of

    common_returns = _collect()
    returns = pd.DataFrame(common_returns).dropna()
    w = dev_weights_of(returns)
    port = _simulate(returns, pd.Series(w), returns.index)
    vt = vol_targeted(port, 0.12)
    return port, vt


def _svg_line(series: "pd.Series", width: int = 900, height: int = 300) -> str:  # type: ignore[name-defined]
    values = (1 + series.fillna(0)).cumprod().tolist()
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = []
    for i, v in enumerate(values):
        x = i / max(len(values) - 1, 1) * width
        y = height - (v - lo) / span * height
        pts.append(f"{x:.1f},{y:.1f}")
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
            f'preserveAspectRatio="none"><polyline fill="none" stroke="#4ade80" '
            f'stroke-width="2" points="{" ".join(pts)}"/></svg>')


def main() -> None:
    import pandas as pd

    honest = json.loads((FOUNDER / "honest-dsr-verdict.json").read_text(encoding="utf-8"))
    combo = json.loads((FOUNDER / "combo-overlay" / "combo-results.json").read_text(encoding="utf-8"))
    parity = json.loads((FOUNDER / "risk-parity-portfolio.json").read_text(encoding="utf-8"))

    g45 = sorted([r for r in honest["all_rows"] if r.get("gate_g4") and r.get("gate_g5")],
                 key=lambda r: -(r["t_stat"] or 0))
    combos = sorted([r for r in combo["results"]
                     if r.get("status") == "OK" and r["t_stat"] is not None
                     and abs(r["t_stat"]) >= 2.5 and (r["max_dd_pct"] or 100) <= 20],
                    key=lambda r: -r["annual_pct"])

    rows = "".join(
        f"<tr><td>{r['name']}</td><td>{r['symbol']}</td><td class='pos'>{r['annual_pct']:+.1f}%</td>"
        f"<td>{r['t_stat']:.2f}</td><td>{r['dsr']:.3f}</td><td class='neg'>{r['max_dd_pct']:.1f}%</td>"
        f"<td>{r['trade_count']}</td></tr>"
        for r in g45
    )
    combo_rows = "".join(
        f"<tr><td>{r['label']}</td><td class='pos'>{r['annual_pct']:+.2f}%</td>"
        f"<td>{r['t_stat']:.2f}</td><td class='ok'>{r['max_dd_pct']:.1f}%</td>"
        f"<td>{r['trade_count']}</td></tr>"
        for r in combos
    )

    try:
        port, vt = _portfolio_equity()
        curve_vt = _svg_line(vt)
        curve_raw = _svg_line(port)
        stats = parity
    except Exception as exc:  # noqa: BLE001 — page must render even without portfolio data
        curve_vt = curve_raw = f"<p class='neg'>portfolio curve unavailable: {exc}</p>"
        stats = parity

    html = f"""<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><title>Founder Results — jev-vibe</title>
<style>
  body {{ font: 14px/1.45 system-ui, sans-serif; color: #e5e7eb; background: #0b1220; margin: 24px; }}
  h1 {{ font-size: 20px; }} h2 {{ font-size: 16px; margin-top: 28px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; }}
  th, td {{ padding: 5px 10px; border-bottom: 1px solid #1f2937; text-align: left; }}
  th {{ color: #9ca3af; font-weight: 600; }}
  .pos {{ color: #4ade80; }} .neg {{ color: #f87171; }} .ok {{ color: #60a5fa; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }}
  .card {{ background: #111a2e; border: 1px solid #1f2937; border-radius: 10px; padding: 12px 16px; min-width: 170px; }}
  .card b {{ display: block; font-size: 22px; }}
  .muted {{ color: #9ca3af; font-size: 12px; }}
</style></head><body>
<h1>Результаты роя стратегий — jev-vibe (30 пар, честный DSR)</h1>
<p class="muted">Данные 2018–2026 · издержки учтены · плечо 1.0 · честный Deflated Sharpe по всем {honest['n_trials_total']} прогонам</p>
<div class="cards">
  <div class="card"><b>{honest['n_trials_total']}</b><span class="muted">прогонов протестировано</span></div>
  <div class="card"><b>{len(g45)}</b><span class="muted">прошли статистику (t≥3 + DSR≥0.95)</span></div>
  <div class="card"><b>{len(combos)}</b><span class="muted">кандидатов с DD≤20% (t≥2.5)</span></div>
  <div class="card"><b class="pos">+{stats['full_voltarget12']['annual_pct']:.1f}%</b><span class="muted">портфель/год (vol-target 12%)</span></div>
  <div class="card"><b class="neg">{stats['full_voltarget12']['max_dd_pct']:.1f}%</b><span class="muted">макс. просадка портфеля</span></div>
</div>

<h2>1. График портфеля (13 стратегий, риск-паритет, vol-target 12%)</h2>
<div style="background:#111a2e;border:1px solid #1f2937;border-radius:10px;padding:10px">
  <div class="muted">Кривая капитала, старт = 1.0. Зелёная — с vol-target (DD 20.4%), серая — сырой портфель.</div>
  <div style="position:relative">{curve_raw.replace('#4ade80', '#374151')}<div style="position:absolute;inset:0">{curve_vt}</div></div>
</div>
<table><tr><th>Окно</th><th>Доходность</th><th>t-стат</th><th>Просадка</th><th>Дней</th></tr>
<tr><td>EVAL 2023–2026 (честно, веса фикс.)</td><td class="pos">+{stats['eval']['annual_pct']:.1f}%</td><td>{stats['eval']['t_stat']:.2f}</td><td class="neg">{stats['eval']['max_dd_pct']:.1f}%</td><td>{stats['eval']['days']}</td></tr>
<tr><td>EVAL + vol-target 12%</td><td class="pos">+{stats['eval_voltarget12']['annual_pct']:.1f}%</td><td>{stats['eval_voltarget12']['t_stat']:.2f}</td><td class="neg">{stats['eval_voltarget12']['max_dd_pct']:.1f}%</td><td>{stats['eval_voltarget12']['days']}</td></tr>
<tr><td>Полное окно + vol-target 12%</td><td class="pos">+{stats['full_voltarget12']['annual_pct']:.1f}%</td><td>{stats['full_voltarget12']['t_stat']:.2f}</td><td class="neg">{stats['full_voltarget12']['max_dd_pct']:.1f}%</td><td>2260</td></tr></table>
<p class="muted">⚠️ Честно: веса портфеля фит на полном окне — есть selection bias. Честная проверка = forward-PAPER (ещё не запущен).</p>

<h2>2. Топ-13 выживших (статистика t≥3 + DSR≥0.95)</h2>
<table><tr><th>Стратегия</th><th>Пара</th><th>Годовая</th><th>t</th><th>DSR</th><th>Макс. просадка</th><th>Сделок</th></tr>{rows}</table>
<p class="muted">Все 13 блокируются только просадкой (41–82%) — поэтому без risk overlay не берутся.</p>

<h2>3. Кандидаты с просадкой под контролем (combo-overlay: vol-target × ddthrottle)</h2>
<table><tr><th>Комбо</th><th>Годовая</th><th>t</th><th>Просадка</th><th>Сделок</th></tr>{combo_rows}</table>

<h2>4. Что дальше</h2>
<p>Единственная честная проверка — <b>forward-PAPER</b>: портфель торгует виртуальными деньгами 60+ дней.
Jev-судья ведёт регим-чек (цена $0.00002/вызов). Реестр Jev: <code>wiki/founder/JEV_IMPLEMENTATION.md</code>.</p>
</body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(f"written: {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
