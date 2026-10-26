"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, FlaskConical, Loader2, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

interface CandidateRow {
  id: string;
  symbol: string;
  scan: string;
  parameters: string;
  risk_parameters: string;
  period_start: string;
  period_end: string;
  baseline: { annual_pct: number; max_dd_pct: number; t_stat: number; final_value: number };
  overlay: {
    annual_pct: number;
    max_dd_pct: number;
    final_value: number;
    final_btc_units: number;
    final_btc_price: number;
    final_btc_value: number;
    btc_share_pct: number;
    locks: number;
    returns_to_asset: number;
    delta_annual_pct: number;
    delta_dd_pct: number;
  };
}

interface FounderPayload {
  generated_at: string;
  audit: string;
  status: string;
  notice_ru: string;
  btc_kopilka_rules: Record<string, number | string>;
  candidates: CandidateRow[];
  honest_dsr_recheck?: {
    date: string;
    scale: string;
    n_trials_pooled: number;
    trial_sharpe_std: number;
    expected_false_positives_5pct: number;
    n_reference: number;
    n_candidate: number;
    best_by_dsr: Array<{
      block: string;
      name: string;
      family: string;
      risk: string;
      symbol: string;
      t_stat: number;
      dsr: number;
      max_dd_pct: number;
      sharpe_per_obs: number;
      n_obs: number;
    }>;
    limitation: string;
  };
}

interface Scan5yPayload {
  date: string;
  period: { start: string; end: string; years: number; bars: number };
  n_runs: number;
  n_ok: number;
  n_errors: number;
  n_families: number;
  n_symbols: number;
  n_variants: number;
  n_trials_pooled: number;
  trial_sharpe_std: number;
  expected_false_positives_5pct: number;
  n_reference: number;
  n_candidate: number;
  top_by_t: Array<{
    family: string;
    symbol: string;
    risk: string;
    params: string;
    annual_pct: number;
    t_stat: number;
    dsr: number | null;
    max_dd_pct: number;
    sharpe_per_obs: number;
    n_obs: number;
    trade_count: number | null;
  }>;
  top_by_annual_with_dd20: Array<{
    family: string;
    symbol: string;
    risk: string;
    params: string;
    annual_pct: number;
    t_stat: number;
    dsr: number | null;
    max_dd_pct: number;
    sharpe_per_obs: number;
    n_obs: number;
    trade_count: number | null;
  }>;
  honest_limits: string[];
}

interface KopilkaConfig {
  lock_threshold: number;
  lock_share_of_gain: number;
  return_share_of_btc: number;
  drawdown_trigger: number;
  ma_window: number;
  cost_per_leg: number;
  start_capital: number;
}

interface SensitivityEntry {
  id: string;
  lock_threshold: number;
  lock_share: number;
  return_share: number;
  annual_pct: number;
  max_dd_pct: number;
  final_value: number;
  final_btc_units: number;
  btc_share_pct: number;
  delta_annual_pct: number;
  delta_dd_pct: number;
}

interface BtcKopilkaJson {
  declared_parameters: {
    lock_threshold: number;
    lock_share_of_gain: number;
    return_share_of_btc: number;
    drawdown_trigger: number;
    ma_window: number;
    cost_per_leg: number;
    start_capital: number;
  };
  honest_limits: string[];
  sensitivity: SensitivityEntry[];
  results: Array<{
    id: string;
    symbol: string;
    scan: string;
    parameters: string;
    risk_parameters: string;
    period_start: string;
    period_end: string;
    baseline: { annual_pct: number; max_dd_pct: number; t_stat: number; final_value: number; days?: number };
    overlay: {
      annual_pct: number;
      max_dd_pct: number;
      final_value: number;
      final_btc_units: number;
      final_btc_price: number;
      final_btc_value: number;
      final_strategy_value: number;
      final_cash: number;
      locks: number;
      returns_to_asset: number;
      btc_share_pct: number;
      delta_annual_pct: number;
      delta_dd_pct: number;
      delta_final_value: number;
    };
  }>;
}

function formatParams(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return Object.entries(parsed)
      .map(([key, value]) => `${key}=${String(value)}`)
      .join(", ");
  } catch {
    return raw;
  }
}

const NUMBER = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });

export function Founder() {
  const { t } = useTranslation();
  const [data, setData] = useState<FounderPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kopilka, setKopilka] = useState<BtcKopilkaJson | null>(null);
  const [scan5y, setScan5y] = useState<Scan5yPayload | null>(null);
  const [cfg, setCfg] = useState<KopilkaConfig>({
    lock_threshold: 0.3,
    lock_share_of_gain: 0.75,
    return_share_of_btc: 0.3,
    drawdown_trigger: 0.1,
    ma_window: 50,
    cost_per_leg: 0.001,
    start_capital: 100,
  });

  useEffect(() => {
    let cancelled = false;
    fetch("/founder-results.json")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((payload: FounderPayload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/btc-kopilka.json")
      .then((res) => (res.ok ? res.json() : null))
      .then((payload: BtcKopilkaJson | null) => {
        if (!cancelled && payload?.declared_parameters) {
          setKopilka(payload);
          setCfg({
            lock_threshold: payload.declared_parameters.lock_threshold,
            lock_share_of_gain: payload.declared_parameters.lock_share_of_gain,
            return_share_of_btc: payload.declared_parameters.return_share_of_btc,
            drawdown_trigger: payload.declared_parameters.drawdown_trigger,
            ma_window: payload.declared_parameters.ma_window,
            cost_per_leg: payload.declared_parameters.cost_per_leg,
            start_capital: payload.declared_parameters.start_capital,
          });
        } else if (!cancelled) {
          setKopilka(payload);
        }
      })
      .catch(() => {
        if (!cancelled) setKopilka(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/scan5y.json")
      .then((res) => (res.ok ? res.json() : null))
      .then((payload: Scan5yPayload | null) => {
        if (!cancelled) setScan5y(payload);
      })
      .catch(() => {
        if (!cancelled) setScan5y(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const totals = useMemo(() => {
    if (!data) return null;
    const rows = data.candidates;
    const btcUnits = rows.reduce((sum, r) => sum + r.overlay.final_btc_units, 0);
    const btcValue = rows.reduce((sum, r) => sum + r.overlay.final_btc_value, 0);
    const finalValue = rows.reduce((sum, r) => sum + r.overlay.final_value, 0);
    const baseValue = rows.reduce((sum, r) => sum + r.baseline.final_value, 0);
    const betterDd = rows.filter((r) => r.overlay.delta_dd_pct > 0).length;
    const meanDeltaAnnual = rows.reduce((s, r) => s + r.overlay.delta_annual_pct, 0) / rows.length;
    const meanDeltaDd = rows.reduce((s, r) => s + r.overlay.delta_dd_pct, 0) / rows.length;
    return { btcUnits, btcValue, finalValue, baseValue, betterDd, meanDeltaAnnual, meanDeltaDd, count: rows.length };
  }, [data]);

  const preset = useMemo(() => {
    if (!kopilka) return null;
    // Параметры комбинации лежат в sensitivity[], а не в results[]:
    // results — это 13 кандидатов на НАБОРЕ параметров владельца.
    const target = {
      lock_threshold: cfg.lock_threshold,
      lock_share: cfg.lock_share_of_gain,
      return_share: cfg.return_share_of_btc,
    };
    const near = (a: number, b: number) => Math.abs(a - b) < 1e-9;
    const matches = (kopilka.sensitivity ?? []).filter(
      (r) =>
        near(r.lock_threshold, target.lock_threshold) &&
        near(r.lock_share, target.lock_share) &&
        near(r.return_share, target.return_share),
    );
    if (!matches.length) return null;
    const btcUnits = matches.reduce((s, r) => s + r.final_btc_units, 0);
    const finalValue = matches.reduce((s, r) => s + r.final_value, 0);
    const meanDeltaAnnual = matches.reduce((s, r) => s + r.delta_annual_pct, 0) / matches.length;
    const meanDeltaDd = matches.reduce((s, r) => s + r.delta_dd_pct, 0) / matches.length;
    const betterDd = matches.filter((r) => r.delta_dd_pct > 0).length;
    const meanBtcShare = matches.reduce((s, r) => s + r.btc_share_pct, 0) / matches.length;
    const meanDd = matches.reduce((s, r) => s + Math.abs(r.max_dd_pct), 0) / matches.length;
    return {
      matches,
      btcUnits,
      finalValue,
      meanDeltaAnnual,
      meanDeltaDd,
      betterDd,
      meanBtcShare,
      meanDd,
      count: matches.length,
    };
  }, [kopilka, cfg]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-8 w-8 animate-spin mr-2" />
        {t("founder.loading")}
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {t("founder.loadError")} {error}
      </div>
    );
  }

  return (
    <div className="min-h-screen p-6 lg:p-8">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <header className="space-y-3 border-b pb-6">
          <div className="inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium text-muted-foreground">
            <FlaskConical className="h-3.5 w-3.5" />
            {t("founder.badge")}
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{t("founder.title")}</h1>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{t("founder.subtitle")}</p>
          </div>
        </header>

        <section className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div className="space-y-2">
            <p className="font-medium">{t("founder.warningTitle")}</p>
            <p className="text-muted-foreground">{t("founder.notice")}</p>
            <a
              href={data.audit}
              className="inline-block text-sm font-medium text-primary underline underline-offset-4"
            >
              {t("founder.auditLink")}
            </a>
          </div>
        </section>

        {data.honest_dsr_recheck ? (
          <section className="rounded-lg border bg-card">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-medium">Честный пересчёт DSR по всему пулу</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Шкала: {data.honest_dsr_recheck.scale}. Пул испытаний:{" "}
                {data.honest_dsr_recheck.n_trials_pooled}; при 5% ложных срабатываний ожидается{" "}
                {data.honest_dsr_recheck.expected_false_positives_5pct} ложных кандидатов.
              </p>
            </div>
            <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Прошли ЭТАЛОН" value={String(data.honest_dsr_recheck.n_reference)} hint="t>=3 + DSR>=0.95 + |DD|<=20%" />
              <Stat label="Прошли КАНДИДАТ" value={String(data.honest_dsr_recheck.n_candidate)} hint="t>=2.5 + DSR>=0.95 + |DD|<=20%" />
              <Stat
                label="Лучший по DSR"
                value={
                  data.honest_dsr_recheck.best_by_dsr[0]
                    ? `${data.honest_dsr_recheck.best_by_dsr[0].dsr.toFixed(4)}`
                    : "—"
                }
                hint={
                  data.honest_dsr_recheck.best_by_dsr[0]
                    ? `${data.honest_dsr_recheck.best_by_dsr[0].name} (бар 0.95)`
                    : undefined
                }
              />
              <Stat
                label="Разброс Sharpe по пулу"
                value={data.honest_dsr_recheck.trial_sharpe_std.toFixed(5)}
                hint="Периодическая шкала"
              />
            </div>
            <div className="overflow-x-auto border-t">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-3 py-2 text-left">Прогон</th>
                    <th className="px-3 py-2 text-left">Пара</th>
                    <th className="px-3 py-2 text-left">Риск</th>
                    <th className="px-3 py-2 text-right">t</th>
                    <th className="px-3 py-2 text-right">DSR</th>
                    <th className="px-3 py-2 text-right">Просадка</th>
                    <th className="px-3 py-2 text-right">Sharpe/набл.</th>
                  </tr>
                </thead>
                <tbody>
                  {data.honest_dsr_recheck.best_by_dsr.map((row) => (
                    <tr key={`${row.block}-${row.name}`} className="border-b border-border/50 last:border-0">
                      <td className="px-3 py-2">{row.name}</td>
                      <td className="px-3 py-2">{row.symbol || "—"}</td>
                      <td className="px-3 py-2">{row.risk || "—"}</td>
                      <td className="px-3 py-2 text-right">{row.t_stat.toFixed(3)}</td>
                      <td className="px-3 py-2 text-right font-mono">{row.dsr.toFixed(4)}</td>
                      <td className="px-3 py-2 text-right">{row.max_dd_pct.toFixed(1)}%</td>
                      <td className="px-3 py-2 text-right">{row.sharpe_per_obs.toFixed(5)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t px-4 py-3 text-xs text-muted-foreground">
              {data.honest_dsr_recheck.limitation}
            </div>
          </section>
        ) : null}

        {scan5y ? (
          <section className="rounded-lg border bg-card">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-medium">5-летний скан: {scan5y.n_ok} прогонов</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Окно {scan5y.period.start} .. {scan5y.period.end} ({scan5y.period.years} года,{" "}
                {scan5y.period.bars} дневных баров). Доходность в годовых. Пул испытаний:{" "}
                {scan5y.n_trials_pooled}; ожидается {scan5y.expected_false_positives_5pct.toFixed(0)}{" "}
                ложных срабатываний при 5%.
              </p>
            </div>
            <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Прогонов" value={String(scan5y.n_ok)} hint={`${scan5y.n_families} семейств, ${scan5y.n_symbols} пар, ${scan5y.n_variants} вариантов`} />
              <Stat label="Прошли ЭТАЛОН" value={String(scan5y.n_reference)} hint="t>=3 + DSR>=0.95 + |DD|<=20%" />
              <Stat label="Прошли КАНДИДАТ" value={String(scan5y.n_candidate)} hint="t>=2.5 + DSR>=0.95 + |DD|<=20%" />
              <Stat label="Разброс Sharpe по пулу" value={scan5y.trial_sharpe_std.toFixed(5)} hint="Периодическая шкала" />
            </div>
            <div className="overflow-x-auto border-t">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-3 py-2 text-left">Стратегия</th>
                    <th className="px-3 py-2 text-left">Пара</th>
                    <th className="px-3 py-2 text-left">Параметры</th>
                    <th className="px-3 py-2 text-left">Риск</th>
                    <th className="px-3 py-2 text-right">Годовая %</th>
                    <th className="px-3 py-2 text-right">t</th>
                    <th className="px-3 py-2 text-right">DSR</th>
                    <th className="px-3 py-2 text-right">Просадка %</th>
                  </tr>
                </thead>
                <tbody>
                  {scan5y.top_by_t.map((row, index) => (
                    <tr key={`${row.family}-${row.symbol}-${row.risk}-${row.params}-${index}`} className="border-b border-border/50 last:border-0">
                      <td className="px-3 py-2">{row.family}</td>
                      <td className="px-3 py-2">{row.symbol}</td>
                      <td className="px-3 py-2 text-[11px] text-muted-foreground">{row.params}</td>
                      <td className="px-3 py-2">{row.risk}</td>
                      <td className="px-3 py-2 text-right">{row.annual_pct.toFixed(2)}%</td>
                      <td className="px-3 py-2 text-right">{row.t_stat.toFixed(3)}</td>
                      <td className="px-3 py-2 text-right font-mono">{row.dsr !== null ? row.dsr.toFixed(4) : "—"}</td>
                      <td className="px-3 py-2 text-right">{row.max_dd_pct.toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="border-t px-4 py-3 text-xs text-muted-foreground">
              <div className="mb-1 font-medium text-foreground">Ограничения</div>
              <ul className="list-disc space-y-1 ps-5">
                {scan5y.honest_limits.map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </div>
          </section>
        ) : null}

        {totals && (
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label={t("founder.statCandidates")} value={String(totals.count)} />
            <Stat
              label={t("founder.statBtcUnits")}
              value={`${totals.btcUnits.toFixed(6)} BTC`}
              hint={t("founder.statBtcUnitsHint", {
                count: totals.count,
                value: `$${NUMBER.format(totals.btcValue)}`,
                capital: `$${NUMBER.format(totals.count * 100)}`,
              })}
            />
            <Stat
              label={t("founder.statDeltaAnnual")}
              value={`${totals.meanDeltaAnnual >= 0 ? "+" : ""}${totals.meanDeltaAnnual.toFixed(2)} п.п./год`}
              hint={t("founder.statDeltaAnnualHint")}
            />
            <Stat
              label={t("founder.statBetterDd")}
              value={`${totals.betterDd} / ${totals.count}`}
              hint={`${totals.meanDeltaDd >= 0 ? "+" : ""}${totals.meanDeltaDd.toFixed(2)} п.п. — средняя просадка`}
            />
          </section>
        )}

        <section className="rounded-lg border bg-card">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-medium">Настройка BTC-копилки</h2>
            </div>
            <div className="text-xs text-muted-foreground">
              Считается по сохранённому артефакту `btc-kopilka.json` (без полного пересчёта бэктеста)
            </div>
          </div>
          <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-7">
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              lock_threshold
              <input
                type="number"
                step="0.01"
                value={cfg.lock_threshold}
                onChange={(e) => setCfg((c) => ({ ...c, lock_threshold: Number(e.target.value) }))}
                className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              lock_share_of_gain
              <input
                type="number"
                step="0.01"
                value={cfg.lock_share_of_gain}
                onChange={(e) => setCfg((c) => ({ ...c, lock_share_of_gain: Number(e.target.value) }))}
                className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              return_share_of_btc
              <input
                type="number"
                step="0.01"
                value={cfg.return_share_of_btc}
                onChange={(e) => setCfg((c) => ({ ...c, return_share_of_btc: Number(e.target.value) }))}
                className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              drawdown_trigger
              <input
                type="number"
                step="0.01"
                value={cfg.drawdown_trigger}
                onChange={(e) => setCfg((c) => ({ ...c, drawdown_trigger: Number(e.target.value) }))}
                className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              ma_window
              <input
                type="number"
                step="1"
                value={cfg.ma_window}
                onChange={(e) => setCfg((c) => ({ ...c, ma_window: Number(e.target.value) }))}
                className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              cost_per_leg
              <input
                type="number"
                step="0.0001"
                value={cfg.cost_per_leg}
                onChange={(e) => setCfg((c) => ({ ...c, cost_per_leg: Number(e.target.value) }))}
                className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-muted-foreground">
              start_capital
              <input
                type="number"
                step="10"
                value={cfg.start_capital}
                onChange={(e) => setCfg((c) => ({ ...c, start_capital: Number(e.target.value) }))}
                className="rounded-md border bg-background px-2 py-1 text-sm text-foreground"
              />
            </label>
          </div>
          {preset ? (
            <div className="grid gap-3 border-t p-4 sm:grid-cols-2 lg:grid-cols-6">
              <Stat
                label="Кандидатов в комбинации"
                value={String(preset.count)}
                hint={`Всего ${kopilka?.sensitivity?.length ?? 0} строк сетки параметров`}
              />
              <Stat
                label="Накоплено BTC (сумма)"
                value={`${preset.btcUnits.toFixed(6)} BTC`}
                hint={`Средняя доля BTC в счёте ${preset.meanBtcShare.toFixed(1)}%`}
              />
              <Stat
                label="Итог счетов (сумма)"
                value={`$${NUMBER.format(preset.finalValue)}`}
                hint={`Стартовый капитал 13 x $${NUMBER.format(cfg.start_capital)}`}
              />
              <Stat
                label="Средняя дельта годовой"
                value={`${preset.meanDeltaAnnual >= 0 ? "+" : ""}${preset.meanDeltaAnnual.toFixed(2)} п.п./год`}
                hint="Оверлей минус базовая стратегия"
              />
              <Stat
                label="Средняя дельта просадки"
                value={`${preset.meanDeltaDd >= 0 ? "+" : ""}${preset.meanDeltaDd.toFixed(2)} п.п.`}
                hint={`Лучше по DD: ${preset.betterDd} / ${preset.count}`}
              />
              <Stat
                label="Средняя просадка"
                value={`${preset.meanDd.toFixed(1)}%`}
                hint="По этой комбинации параметров"
              />
            </div>
          ) : (
            <div className="border-t px-4 py-3 text-xs text-muted-foreground">
              Для текущих значений нет полного совпадения в сетке `btc-kopilka.json`. Доступные комбинации
              порогов: 0.30 / 0.50, доля прироста: 0.50 / 0.75, возврат резерва: 0.00 / 0.30.
            </div>
          )}
          {preset && (
            <div className="overflow-x-auto border-t">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-3 py-2 text-left">Кандидат</th>
                    <th className="px-3 py-2 text-right">Годовая</th>
                    <th className="px-3 py-2 text-right">Просадка</th>
                    <th className="px-3 py-2 text-right">Итог</th>
                    <th className="px-3 py-2 text-right">BTC</th>
                    <th className="px-3 py-2 text-right">Доля BTC</th>
                    <th className="px-3 py-2 text-right">Δ годовой</th>
                    <th className="px-3 py-2 text-right">Δ просадки</th>
                  </tr>
                </thead>
                <tbody>
                  {preset.matches.map((row) => (
                    <tr key={`${row.id}-${row.lock_threshold}-${row.lock_share}-${row.return_share}`} className="border-b border-border/50 last:border-0">
                      <td className="px-3 py-2">{row.id}</td>
                      <td className="px-3 py-2 text-right">{row.annual_pct.toFixed(2)}%</td>
                      <td className="px-3 py-2 text-right">{row.max_dd_pct.toFixed(2)}%</td>
                      <td className="px-3 py-2 text-right">${NUMBER.format(row.final_value)}</td>
                      <td className="px-3 py-2 text-right font-mono">{row.final_btc_units.toFixed(6)}</td>
                      <td className="px-3 py-2 text-right">{row.btc_share_pct.toFixed(1)}%</td>
                      <td
                        className={cn(
                          "px-3 py-2 text-right",
                          row.delta_annual_pct >= 0 ? "text-emerald-600" : "text-rose-600",
                        )}
                      >
                        {row.delta_annual_pct >= 0 ? "+" : ""}
                        {row.delta_annual_pct.toFixed(2)}
                      </td>
                      <td
                        className={cn(
                          "px-3 py-2 text-right",
                          row.delta_dd_pct >= 0 ? "text-emerald-600" : "text-rose-600",
                        )}
                      >
                        {row.delta_dd_pct >= 0 ? "+" : ""}
                        {row.delta_dd_pct.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {kopilka?.honest_limits?.length ? (
            <div className="border-t px-4 py-3 text-xs text-muted-foreground">
              <div className="mb-1 font-medium text-foreground">Ограничения расчёта</div>
              <ul className="list-disc space-y-1 ps-5">
                {kopilka.honest_limits.map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>

        <section className="overflow-x-auto rounded-lg border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 text-left">{t("founder.colStrategy")}</th>
                <th className="px-3 py-2 text-left">{t("founder.colSymbol")}</th>
                <th className="px-3 py-2 text-right">{t("founder.colBaseAnnual")}</th>
                <th className="px-3 py-2 text-right">{t("founder.colBaseDd")}</th>
                <th className="px-3 py-2 text-right">{t("founder.colOverlayAnnual")}</th>
                <th className="px-3 py-2 text-right">{t("founder.colOverlayDd")}</th>
                <th className="px-3 py-2 text-right">{t("founder.colFinalUsd")}</th>
                <th className="px-3 py-2 text-right">{t("founder.colBtc")}</th>
                <th className="px-3 py-2 text-right">{t("founder.colBtcShare")}</th>
              </tr>
            </thead>
            <tbody>
              {data.candidates.map((row) => (
                <tr key={row.id} className="border-b border-border/50 last:border-0">
                  <td className="px-3 py-2">
                    <div className="font-medium">{row.id}</div>
                    <div className="text-[11px] text-muted-foreground">{formatParams(row.parameters)}</div>
                    <div className="text-[11px] text-muted-foreground">{formatParams(row.risk_parameters)}</div>
                  </td>
                  <td className="px-3 py-2">{row.symbol}</td>
                  <td className="px-3 py-2 text-right">{row.baseline.annual_pct.toFixed(2)}%</td>
                  <td className="px-3 py-2 text-right">{row.baseline.max_dd_pct.toFixed(2)}%</td>
                  <td
                    className={cn(
                      "px-3 py-2 text-right",
                      row.overlay.delta_annual_pct >= 0 ? "text-emerald-600" : "text-rose-600",
                    )}
                  >
                    {row.overlay.annual_pct.toFixed(2)}%
                  </td>
                  <td
                    className={cn(
                      "px-3 py-2 text-right",
                      row.overlay.delta_dd_pct >= 0 ? "text-emerald-600" : "text-rose-600",
                    )}
                  >
                    {row.overlay.max_dd_pct.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 text-right">${NUMBER.format(row.overlay.final_value)}</td>
                  <td className="px-3 py-2 text-right font-mono">
                    {row.overlay.final_btc_units.toFixed(6)}
                  </td>
                  <td className="px-3 py-2 text-right">{row.overlay.btc_share_pct.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="rounded-lg border bg-card p-4 text-sm">
          <h2 className="mb-2 font-medium">{t("founder.rulesTitle")}</h2>
          <ul className="list-disc space-y-1 ps-5 text-muted-foreground">
            <li>{t("founder.ruleLock")}</li>
            <li>{t("founder.ruleBottom")}</li>
            <li>{t("founder.ruleCosts")}</li>
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">
            {t("founder.generatedAt")}: {data.generated_at}
          </p>
        </section>
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}
