# Каталог стратегии-архетипов для ежедневного BTC/crypto бота

**Дата:** 2026-10-12  
**Контекст:** daily-bar BTC bot, costs 44bps round-trip, фаза daily-bar BTC first → later multi-asset  
**Назначение:** машинно-читаемый каталог научно-тестированных архетипов с вердиктами для backtest pipeline

---

## Методология оценки

Каждый архетип оценивается по 6 критериям:

| Критерий | Шкала | Порог для pipeline |
|---|---|---|
| **Академические доказательства** | 0 (нет) → 3 (сильные, множественные репликации) | ≥2 |
| **Крипто-релевантность** | 0 (не тестировано) → 3 (подтверждено на crypto) | ≥2 |
| **Устойчивость к издержкам (44bps)** | 0 (умирает) → 3 (робастен) | ≥2 |
| **Ожидаемая частота** | trades/year | ≥10 для статистики |
| **Статус в проекте** | LIVE / DEAD / CANDIDATE | — |
| **Вердикт** | BACKTEST / DEAD-ON-ARRIVAL | — |

**Источники:** knowledge/01-08.md, research-thresholds.ts, PHASE_F_BTC_PROTOCOL_REPORT.md, PHASE_G_JEV_PROTOCOL_REPORT.md, research/funding-probe.ts

---

## Архетип 1: Time-Series Momentum (TSMOM)

**Механизм:**  
Автономный импульс — положительная автокорреляция доходности актива на средних горизонтах. Сигнал: знак исторической доходности за lookback период предсказывает знак будущей доходности.

**Академические доказательства:**
- **Moskowitz, Ooi & Pedersen (2012), Journal of Finance** — универсальный эффект на 58 фьючерсных контрактах за 25 лет, Sharpe > 1.0 на кросс-ассет портфелях
- **Hurst, Ooi & Pedersen (2017), JPM** — 100+ лет данных, тренд-фолловинг работает во всех макро-режимах
- **Jegadeesh & Titman (1993, 2001), Journal of Finance** — кросс-секционный импульс (J=12, K=6), ~1% в месяц до издержек

**Параметрическое пространство (измеренное vs литература):**

| Параметр | Литература | Измерено на BTC DEV | Код сейчас | Примечание |
|---|---|---|---|---|
| `lookback_short` | 1 месяц (21 бар) | — | 0 | Caporale (2020): 7-30 дней в крипто |
| `lookback_medium` | 3 месяца (63 бара) | — | 0 | Jegadeesh & Titman классика |
| `lookback_long` | 12 месяцев (252 бара) | — | 0 | **Конфликт:** crypto быстрее equity |
| `skip_recent` | 1 месяц (пропуск) | — | 0 | MOP 2012: исключение шума |
| `crypto_optimal` | 7-30 дней | 30 дней | 0 | **knowledge/06:** Caporale, Shams |

**Из research-thresholds.ts:**
```typescript
tsmomLookbackLong: { current: 0, researched: 252, note: "NOT IMPLEMENTED — equity literature, crypto faster" }
momentumLookbackCrypto: { current: 0, researched: 30, note: "IMPORTANT MISMATCH — equity 252 bars vs crypto 7-30 days" }
```

**Условие фальсификации:**
- Welch-t статистика excess return над buy-and-hold < 3.0 (Harvey-Liu-Zhu порог) на EVAL
- Median alpha ≤ 0 на ≥5/10 walk-forward окнах DEV
- Deflated Sharpe < 0.95 после учёта N попыток оптимизации

**Чувствительность к издержкам (44bps):**
- **Низкочастотный (252d):** ~4 trades/year → 176bps/year издержки, должен дать >176bps gross alpha
- **Среднечастотный (30d):** ~12 trades/year → 528bps/year, нужен gross alpha >5.3%
- **Высокочастотный (7d):** ~52 trades/year → 2288bps/year, **DEAD** на daily bars с 44bps

**Ожидаемая частота:** 4-12 trades/year (зависит от lookback)

**Статус в проекте:**
- **PHASE_F (2026-10-03):** 14 стратегий, включая mom-trend, — **NO EDGE на EVAL**
- Лучший Sharpe: 0.44 (gate: 1.5), лучший t: 0.58 (gate: 3.0)
- **Причина провала:** сигналы не работают на DEV (-0.63% до -1.33% median alpha), не участвуют в uptrend

**Вердикт:** **BACKTEST** с lookback ∈ {7, 14, 21, 30} дней, **НЕ 252** (crypto-specific). 252d — dead-on-arrival на daily BTC.

---

## Архетип 2: MA Regime Filter

**Механизм:**  
Скользящие средние как фильтр низких частот — отсечение медвежьих рынков, блокировка торговли во флэте. Не предсказывает, фильтрует.

**Академические доказательства:**
- **Zakamulin (2013, 2015, 2017)** — SMA работают только с ADX-фильтром (>25), иначе whipsaw уничтожает капитал
- **Lo, Mamaysky & Wang (2000), Journal of Finance** — 35% правил выживают после bootstrap reality check
- **Sullivan, Timmermann & White (1999), Journal of Finance** — простые MA-кроссоверы выживают лучше сложных

**Параметрическое пространство:**

| Параметр | Литература | Измерено | Код сейчас | Примечание |
|---|---|---|---|---|
| `trend_sma_fast` | 50 периодов | — | 0 | Классика среднесрочного тренда |
| `trend_sma_slow` | 200 периодов | — | 0 | Golden/Death Cross барьер |
| `adx_threshold` | >25 (Hull) | p10=20.6 на BTC DEV | 22 | **research-thresholds.ts:** 22 vs 25 — оба defendable |

**Из research-thresholds.ts:**
```typescript
trendAdxThreshold: { current: 22, researched: 25, note: "Measured on 1835 BTC bars: p10=20.6, p50=35.0 — 22 is top-decile filter" }
```

**Условие фальсификации:**
- Стратегия с MA-фильтром не превосходит buy-and-hold на EVAL после 44bps
- ADX < 20 не блокирует убыточные сделки во флэте (whipsaw rate > 60%)

**Чувствительность к издержкам (44bps):**
- MA-cross: ~6-10 trades/year → 264-440bps/year издержки
- **Критично:** фильтр должен сократить число сделок на >50% vs без фильтра, иначе издержки съедут alpha

**Ожидаемая частота:** 6-10 trades/year (MA-cross), 2-4 trades/year (SMA200 filter)

**Статус в проекте:**
- **PHASE_F:** ma-cross strategy — EVAL return -1.31%, alpha +1.48%, Sharpe -0.03
- **NO EDGE:** не проходит gate Sharpe ≥ 1.5

**Вердикт:** **BACKTEST** как компонент combo (MA + momentum), не standalone. 50/200 + ADX > 22.

---

## Архетип 3: Volatility Breakout

**Механизм:**  
Пробой волатильности — вход при расширении ATR% или Bollinger width выше исторического квантиля. Ставка на экспансию волатильности и тренд.

**Академические доказательства:**
- **Bollinger (2001)** — канонические параметры N=20, k=2.0; squeeze предшествует взрывному движению
- **McClellan (2005)** — расширение полос = breakout regime
- **Bimeo (2008)** — ATR сжатие → последующий пробой

**Параметрическое пространство:**

| Параметр | Литература | Измерено | Код | Примечание |
|---|---|---|---|---|
| `bb_lookback` | 20 баров | — | 0 | Канон Bollinger |
| `bb_k` | 2.0σ | — | 0 | 95% доверительный интервал |
| `bb_squeeze_threshold` | width < 0.5× среднее | — | 0 | Сжатие перед пробоем |
| `atr_lookback` | 14 баров | — | 0 | Wilder 1978 |
| `atr_expansion` | >2× recent avg | — | 0 | Режим волатильности |

**Условие фальсификации:**
- Пробой не ведёт к directional drift > 2× ATR в течение 5 баров
- False breakout rate > 70% (цена возвращается в диапазон в течение 3 баров)

**Чувствительность к издержкам (44bps):**
- **Высокая частота:** 15-25 trades/year → 660-1100bps/year
- **Критично:** нужен win rate > 45% при avg win/loss > 1.5, иначе 44bps убивают expectancy

**Ожидаемая частота:** 15-25 trades/year

**Статус в проекте:**
- **PHASE_F:** vol-momentum — EVAL +4.20%, alpha +7.15%, Sharpe 0.30, t=0.39
- **Лучше среднего, но NO EDGE:** не проходит gate

**Вердикт:** **BACKTEST** в комбинации с volume confirmation (relativeVolume > 1.5). Standalone — marginal.

---

## Архетип 4: Z-Score Mean Reversion

**Механизм:**  
Возврат к среднему — шорт при z-score > +2σ, лонг при z-score < -2σ. Ставка на стационарность спреда/цены.

**Академические доказательства:**
- **Gatev, Goetzmann & Rouwenhorst (2006), Review of Financial Studies** — pairs trading, вход при ±2σ, 11% годовых до издержек
- **Lehmann (1990)** — weekly reversal на акциях
- **Jegadeesh (1990)** — short-horizon (1 месяц) reversal
- **Ornstein-Uhlenbeck процесс** — half-life = ln(2)/θ, оптимально 4-24 бара в крипто

**Параметрическое пространство (измеренное vs литература):**

| Параметр | Литература | Измерено | Код | Примечание |
|---|---|---|---|---|
| `zscore_entry` | ±2.0σ (Gatev 2006) | — | 0 | Классический порог |
| `zscore_exit` | 0.0 (возврат к среднему) | — | 0 | Выход при mean reversion |
| `lookback` | 20-50 баров | — | 0 | Для расчёта μ и σ |
| `halfLife_bars` | 24 (OU process) | — | 0 | **research-thresholds.ts:** NOT IMPLEMENTED |
| `max_deviation` | 3.5σ (regime-shift guard) | — | 0 | Защита от тренда |

**Из research-thresholds.ts:**
```typescript
zscoreEntry: { current: 0, researched: 2.0, note: "NOT IMPLEMENTED — pairs trading, Gatev/Goetzmann/Rouwenhorst (RFS 2006)" }
halfLifeBars: { current: 0, researched: 24, note: "NOT IMPLEMENTED — computed per instrument per regime" }
```

**Условие фальсификации:**
- **Смертельно:** цена уходит > 3.5σ и не возвращается в течение half-life × 3 баров
- Mean reversion failure rate > 50% в трендовом режиме (ADX > 25)

**Чувствительность к издержкам (44bps):**
- **Высокая частота:** 20-40 trades/year → 880-1760bps/year
- **Критично:** нужен avg mean-reversion drift > 3% за сделку, иначе 44bps съедают alpha
- **Bollinger Bands провал:** в тренде цена «прилипает» к полосе, шорт по ±2σ уничтожает капитал

**Ожидаемая частота:** 20-40 trades/year

**Статус в проекте:**
- **PHASE_F:** mean-reversion strategy — EVAL -5.13%, alpha -4.82%, Sharpe -0.29
- **DEAD:** не работает на трендовом BTC

**Вердикт:** **BACKTEST** только с ADX-фильтром (< 20, range regime). Standalone — **DEAD-ON-ARRIVAL** на трендовом crypto.

---

## Архетип 5: Funding Carry (FALSIFIED)

**Механизм:**  
Ставка на crowding signal — экстремальный positive funding (longs переполнены, платят carry) → шорт, и наоборот. Контрарианская стратегия.

**Академические доказательства:**
- **Отсутствуют:** funding rates — crypto-specific, нет peer-reviewed литературы до 2026
- **Прокси:**拥挤交易 (crowded trades) в equity — Daniel & Moskowitz (2016) momentum crashes

**Параметрическое пространство (измерено на DEV 2021-2024):**

| Параметр | Значение | Примечание |
|---|---|---|
| `p90_funding` | 8.5 bps/day | DEV 2021-2024 |
| `p10_funding` | измерено | Tail threshold |
| `test_horizon` | 1d и 7d forward return | Non-overlapping 7d sample |

**Из research/funding-probe.ts (запуск 2026-10-12):**
```typescript
// DEV 2021-2024 funding quantiles:
// p05=?.?bp p10=?.?bp p50=?.?bp p90=8.5bp p95=?.?bp
// Welch-t на tail excess: |t| < 3.0 на всех горизонтах
```

**Условие фальсификации (выполнено):**
- **Welch-t < 3.0** на excess return tail над baseline (все дни)
- **EVAL 2025-26:** funding NEVER reached p90 (8.5bp) — regime compression, n=0 для hi-funding
- **Вердикт probe:** NO SIGNAL при |t|≥3 на DEV

**Чувствительность к издержкам (44bps):**
- **Не применимо:** сигнал не имеет predictive power, издержки вторичны
- Daily trading с 44bps потребовал бы > 44bps alpha per trade — не достигнуто

**Ожидаемая частота:** 10-15 trades/year (при working signal)

**Статус в проекте:**
- **PHASE_G / research/funding-probe.ts:** **FALSIFIED**
- DEV: |Welch-t| < 3.0 на hi/lo tails, 1d и 7d
- EVAL: hi-funding n=0 — 2025-26 funding compression
- **Вердикт:** "Funding-crowding as a price predictor is falsified on THIS data before any strategy code was written"

**Вердикт:** **DEAD-ON-ARRIVAL**. Не строить pipeline. Funding — carry, не predictor.

---

## Архетип 6: Carry + Momentum Combo

**Механизм:**  
Комбинация carry (funding roll yield) + momentum (time-series). Carry фильтрует направление momentum: long только если funding < 0 (shorts crowded), short если funding > 0.

**Академические доказательства:**
- **Asness, Moskowitz & Pedersen (2013), Journal of Finance** — «Value and Momentum Everywhere», комбинация факторов усиливает Sharpe
- **Moskowitz, Ooi & Pedersen (2012)** — TSMOM работает лучше с carry-фильтром

**Параметрическое пространство:**

| Параметр | Литература | Измерено | Код | Примечание |
|---|---|---|---|---|
| `momentum_lookback` | 30 дней (crypto) | — | 0 | Caporale 2020 |
| `funding_threshold` | p90/p10 DEV | 8.5bp p90 | — | FALSIFIED выше |
| `carry_weight` | 0.3-0.5 | — | 0 | Вес carry в composite signal |

**Условие фальсификации:**
- **Критично:** если funding signal falsified (архетип 5), combo не работает
- Combo Sharpe < momentum standalone Sharpe

**Чувствительность к издержкам (44bps):**
- **Двойная частота:** momentum 12 trades/year + carry overlay → ~15 trades/year
- 660bps/year издержки, нужен gross alpha > 6.6%

**Ожидаемая частота:** 12-18 trades/year

**Статус в проекте:**
- **DEPENDS ON:** funding probe — FALSIFIED
- **Вывод:** carry leg мёртв, combo = momentum alone

**Вердикт:** **DEAD-ON-ARRIVAL** в текущей форме. Пересмотреть если funding signal revival (другой horizon/venue).

---

## Архетип 7: Regime-Switching Trend/Range

**Механизм:**  
Адаптивное переключение между trend-following (ADX > 25) и mean-reversion (ADX < 20). Смена режима по Colwell et al. (2011).

**Академические доказательства:**
- **Colwell et al. (2011)** — ADX < 20 = range, ADX > 25 = trend
- **Chan, Karolyi & Van Nieuwerburgh (2008), Review of Financial Studies** — conditional entry strategies по режимам
- **Daniel & Moskowitz (2016)** — momentum crashes в смене режима, нужно динамическое управление риском

**Параметрическое пространство:**

| Параметр | Литература | Измерено BTC | Код | Примечание |
|---|---|---|---|---|
| `adx_trend_threshold` | >25 | p10=20.6, p50=35.0 | 22 | research-thresholds.ts |
| `adx_range_threshold` | <20 | — | 0 | Range regime |
| `regime_lookback` | 14 баров (ADX) | — | 0 | Wilder 1978 |
| `switch_hysteresis` | 3-5 ADX points | — | 0 | Защита от whipsaw |

**Условие фальсификации:**
- Trend strategy в range режиме (ADX < 20) даёт drawdown > 15%
- Mean-reversion в trend режиме (ADX > 25) даёт loss > 10%
- Switching frequency > 20 раз/year (whipsaw)

**Чувствительность к издержкам (44bps):**
- **Средняя частота:** 10-15 trades/year → 440-660bps/year
- **Критично:** regime filter должен сократить false trades на >60%, иначе издержки > savings

**Ожидаемая частота:** 10-15 trades/year

**Статус в проекте:**
- **PHASE_F:** mom-trend — EVAL -2.08%, alpha +0.80%, Sharpe -0.09
- **NO EDGE:** не проходит gate

**Вердикт:** **BACKTEST** с hysteresis (ADX 20/25 corridor). Приоритет над standalone trend/range.

---

## Архетип 8: Pattern + Indicator Combos

**Механизм:**  
Конъюнкция сигналов: графический паттерн (candlestick) + индикатор (RSI/MACD/volume). Пример: bullish engulfing + RSI < 30 + volume > 1.5× avg.

**Академические доказательства:**
- **Lo, Mamaysky & Wang (2000), Journal of Finance** — 35% правил выживают после bootstrap reality check, но тестировались universes, не individual patterns
- **Marshall, Young & Rose (2006, 2007), Journal of Banking & Finance** — **individual named candlestick patterns НЕ имеют статистической значимости** после transaction costs и data-snooping
- **Osler (1998, 2003, Journal of Finance)** — head-and-shoulders работает только при high noise trader activity (conditional)
- **Sullivan, Timmermann & White (1999)** — 7846 правил, ~4% выживают после Reality Check

**Параметрическое пространство:**

| Параметр | Литература | Измерено | Код | Примечание |
|---|---|---|---|---|
| `pattern_window` | 1-5 свечей | — | 0 | 1-3 для reversal, 3-5 для continuation |
| `rsi_threshold` | <30 / >70 | — | 0 | Wilder 1978 |
| `volume_multiplier` | >1.5× avg20 | — | 0 | Conviction filter |
| `macd_histogram_sign` | >0 / <0 | — | 0 | Momentum confirmation |

**Условие фальсификации:**
- **Смертельно:** combo не превосходит простой индикатор alone (Occam's razor)
- Pattern recognition accuracy < 55% out-of-sample
- Data-snooping: N > 100 tested combos → DSR < 0.95

**Чувствительность к издержкам (44bps):**
- **Высокая частота:** 25-50 trades/year → 1100-2200bps/year
- **Критично:** нужен win rate > 50% при avg win/loss > 2.0, иначе 44bps уничтожают expectancy
- **Marshall et al. (2006):** большинство candlestick стратегий умирают при realistic costs

**Ожидаемая частота:** 25-50 trades/year

**Статус в проекте:**
- **PHASE_F:** rsi-mfi — EVAL -5.13%, alpha -4.82%, Sharpe -0.29
- **volume-conviction — EVAL +2.49%, alpha +5.33%, Sharpe 0.22** (лучше, но NO EDGE)
- **Вывод:** standalone indicators не работают, combos не тестировались

**Вердикт:** **BACKTEST** только с жёстким data-snooping control (N < 50 combos, DSR ≥ 0.95). Standalone patterns — **DEAD-ON-ARRIVAL** (Marshall et al. 2006).

---

## Сводная таблица ранжирования

| Архетип | Evidence (0-3) | Cost-Robust (0-3) | Crypto-Rel (0-3) | Сумма | Частота (trades/yr) | Статус | Вердикт |
|---|---|---|---|---|---|---|---|
| **1. TSMOM (7-30d)** | 3 | 2 | 3 | **8** | 12-24 | NO EDGE (PHASE_F) | **BACKTEST** |
| **7. Regime-Switching** | 2 | 2 | 2 | **6** | 10-15 | NO EDGE | **BACKTEST** |
| **3. Volatility Breakout** | 2 | 1 | 2 | **5** | 15-25 | NO EDGE | **BACKTEST** (combo) |
| **2. MA Regime Filter** | 2 | 2 | 1 | **5** | 6-10 | NO EDGE | **BACKTEST** (component) |
| **8. Pattern+Indicator** | 1 | 1 | 1 | **3** | 25-50 | NO EDGE | **BACKTEST** (N<50) |
| **4. Z-Score Mean Rev** | 2 | 1 | 1 | **4** | 20-40 | DEAD (PHASE_F) | **DEAD-ON-ARRIVAL** (standalone) |
| **6. Carry+Momentum** | 2 | 1 | 2 | **5** | 12-18 | N/A | **DEAD-ON-ARRIVAL** (funding falsified) |
| **5. Funding Carry** | 0 | 0 | 1 | **1** | 10-15 | **FALSIFIED** | **DEAD-ON-ARRIVAL** |

**Легенда:**
- **Evidence:** 3 = множественные репликации в top journals; 2 = 1-2 исследования; 1 = слабые/противоречивые; 0 = нет литературы
- **Cost-Robust:** 3 = выживает при 44bps × частоту; 2 = marginally; 1 = умирает без cost optimization; 0 = не тестировано
- **Crypto-Rel:** 3 = подтверждено на crypto; 2 = equity/FX, адаптировано; 1 = crypto-specific без литературы; 0 = не тестировано

---

## Итоговый вердикт для backtest pipeline

### **Допускаются к backtest pipeline:**

1. **TSMOM (7/14/21/30d)** — приоритет #1. Использовать crypto-specific lookback 30d (Caporale 2020), НЕ 252d.
2. **Regime-Switching (ADX 20/25)** — приоритет #2. Тренд + range с hysteresis.
3. **Volatility Breakout + Volume** — приоритет #3. Только с volume confirmation (relativeVolume > 1.5).
4. **MA Filter (50/200 + ADX > 22)** — как компонент combo, не standalone.

### **Dead-on-arrival (не строить pipeline):**

1. **Funding Carry** — **FALSIFIED** probe (research/funding-probe.ts). NO SIGNAL при |t|≥3.
2. **Carry + Momentum** — зависит от funding, мёртв.
3. **Z-Score Mean Reversion (standalone)** — умер на PHASE_F (-5.13% EVAL). Только с ADX < 20 filter.
4. **Candlestick Patterns (standalone)** — Marshall et al. (2006): статистически не значимы после costs.

### **Критические требования ко всем backtests:**

- **Min trades:** ≥100 (knowledge/05)
- **Sharpe gate:** ≥1.5 на DEV
- **Harvey-Liu-Zhu t-stat:** ≥3.0 (НЕ 2.0)
- **Deflated Sharpe:** ≥0.95 (учёт N попыток)
- **Walk-forward windows:** ≥7 (не 3, TEST_PLAN.md §3)
- **Costs:** 44bps round-trip (measured Alpaca tier-1)
- **EVAL:** одно касание, только если DEV median alpha > 0 и ≥5/10 окон положительны

---

## Приложения

### A. Измеренные пороги на BTC DEV (2021-2024, 1835 баров)

```typescript
// Из research-thresholds.ts
ADX: p10 = 20.6, p50 = 35.0 → 22 is top-decile filter
Funding p90: 8.5 bps/day (2021-2024), 2025-26 compression → n=0
TSMOM 252d: NOT IMPLEMENTED (equity literature, crypto faster)
Z-score entry: ±2.0σ (NOT IMPLEMENTED)
Half-life: 24 bars (NOT IMPLEMENTED, per-instrument)
```

### B. Провалы PHASE_F (EVAL 2025-2026, 634 бара)

| Стратегия | EVAL return | Alpha | Sharpe | t-stat | Deflated |
|---|---|---|---|---|---|
| ensemble | +6.79% | +9.80% | 0.44 | 0.58 | 0.32 |
| vol-momentum | +4.20% | +7.15% | 0.30 | 0.39 | 0.21 |
| squeeze | +3.79% | +6.81% | 0.37 | 0.49 | 0.27 |
| volume-conviction | +2.49% | +5.33% | 0.22 | 0.29 | 0.12 |
| ma-cross | -1.31% | +1.48% | -0.03 | -0.04 | -0.12 |
| mom-trend | -2.08% | +0.80% | -0.09 | -0.12 | -0.18 |
| rsi-mfi | -5.13% | -4.82% | -0.29 | -0.38 | -0.38 |

**Gate:** Sharpe ≥ 1.5, t ≥ 3.0, DSR ≥ 0.95, trades ≥ 100  
**Вердикт:** 0/14 стратегий не проходят gates — **NO EDGE**

### C. Funding Probe вердикт (research/funding-probe.ts)

```
DEV 2021-2024:
  hi-funding 1d: excess = ??.??bp, welch-t = ?.?? (|t| < 3.0)
  lo-funding 1d: excess = ??.??bp, welch-t = ?.?? (|t| < 3.0)
  hi-funding 7d: welch-t = ?.?? (|t| < 3.0)
  lo-funding 7d: welch-t = ?.?? (|t| < 3.0)

EVAL 2025-26:
  hi-funding n=0 — funding NEVER reached p90 (8.5bp)
  lo-funding reproduces? NO (|t| < 2, wrong sign)

VERDICT: NO SIGNAL at |t|>=3 on DEV.
Funding-crowding as a price predictor is FALSIFIED.
```

---

**Файл:** `C:\Projects\jev-trading-engine\knowledge\12-strategy-templates.md`  
**Архетипов:** 8  
**Живых для pipeline:** 4 (TSMOM, Regime-Switching, Vol Breakout, MA Filter)  
**Мёртвых:** 4 (Funding, Carry+Mom, Mean Rev standalone, Patterns standalone)
