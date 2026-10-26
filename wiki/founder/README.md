# FOUNDER TRANSFER — what came from jev-trading-engine, and why

This branch carries the **knowledge and discipline** from the founder's original project
`C:\Projects\jev-trading-engine` (26 014 lines TypeScript, 41 test files, 58 measured runs)
into Vibe-Trading's 522 702-line Python stack. **No engine code was moved** — almost all of
it is superseded by what is already here. What moved is what Vibe-Trading does not have.

---

## What this adds to Vibe-Trading

### `docs/founder/knowledge/` — 14 academic documents (4 154 lines)

Momentum, mean-reversion, candlestick patterns, position sizing (Kelly), statistical
validation, crypto-specific evidence, **skepticism and failure modes**, how to formulate
questions for a judgment LLM, candlestick and indicator evidence with verdict tables,
a machine-readable strategy archetype catalogue, Jev probabilities and confidence, a
reference-repo survey, and a gap audit. **Vibe-Trading has no equivalent.**

### `docs/founder/archetypes/` — 8 strategy archetypes with verdicts

Each archetype carries 6 criteria (academic evidence ≥2, crypto relevance ≥2, robustness
against 44 bps round-trip ≥2, expected trade frequency ≥10/year, status, verdict). This
answers "which strategies are worth testing" — a question the 478-factor Alpha Zoo does
not answer on its own.

### `docs/founder/gates/EDGE_DISTANCE.md` — the eight-gate ladder

G1 walk-forward alpha > 0 · G2 ≥ 100 trades · G3 Sharpe(EVAL) ≥ 1.5 · **G4 t ≥ 3.0
(Harvey-Liu-Zhu 2016)** · G5 Deflated Sharpe ≥ 0.95 · G6 costs beat 44 bps · G7 transfer
across ≥ 5 assets · G8 forward PAPER ≥ 60 days with ECE ≤ 0.10. A candidate only becomes
a CANDIDATE when all eight pass. **Vibe-Trading's roadmap has no fixed threshold.**

### `docs/founder/preregistration/` — 14 pre-registrations

Rules written **before** looking at results. The parent project's P3 predicted 17.9%/yr,
its own artifact called it an upper bound, the pre-registered basis check came back
**negative 3%/yr** — and the honest conclusion was recorded. Pre-registration is what
made that reversal possible.

### `docs/founder/results-json/` — 58 measured artifacts

Fifty-eight runs, each with a verdict, all in git. **A library of what does not work**
on crypto with 44 bps of round-trip costs: funding carry falsified, small-cap effect not
confirmed (t = −0.02), community library 0/23, Jev calibration ECE 0.51. Cheaper to read
than to re-run.

### `docs/founder/phases/` — 28 phase reports

The full walk, from the first Alpaca paper bot through the honest negative results.

### `docs/founder/lessons/` — process lessons, including five data defects

Five data defects the parent project found and fixed, each one a silent failure that a
normal integrity check cannot catch:

1. Funding pays 3×/day → duplicate days in the daily axis.
2. `PointInTime.valueAt` / `days()` do not exist — the wrong API surface.
3. Position step keyed on the symbol's spelling (`BTC-USD` got step 1 → 0 fills).
4. Data loaders that read `bars` directly, while the file carries `raw.bars`.
5. **`complete=true` written on every save, checked as freshness** — all three Binance
   downloaders froze four days in the past and nothing reported an error.

### `docs/founder/MASTER_TASK.md` — the canon

Working rules that override everything: the founder decides, you build. Three hard stops
(after audit, before venue choice, **before LIVE**). Honesty: anything unverifiable is
labelled UNVERIFIED; never invent API shapes, numbers, benchmarks or results; never claim
a strategy is profitable. Passing tests does NOT authorize real-money trading.

### `docs/founder/jev_adapter.py` — Typesafe Jev adapter (prototype)

A minimal, documented Python adapter for the Typesafe `/v1/systemone` endpoint: what the
request looks like, what Jev answers, how to pull probabilities out of a low-confidence
``no_decision``. **Jev is not yet wired into `src/providers/` — this is a prototype, not
a registered provider.** The calibration history is recorded in the docstring.

### `docs/founder/PATH_TO_WEALTH.md` and `FINAL_REPORT.md`

The honest verdict the parent project reached, in money and time: at 5%/yr, $100 → $100k
takes **143 years**. No edge survives the eight gates in the data available; four ideas
were tested and all four are negative. Three options for the founder, per the plan's stop
rule.

---

## What was NOT moved

- The 26 014-line TypeScript engine — almost all of it is superseded by Vibe-Trading.
- The HTML results panel — Vibe-Trading has React 19 and 11 UI languages.
- The hand-rolled statistics — Vibe-Trading has `src/quantlib/multipletesting.py` with
  DSR, PSR, PBO and Benjamini-Hochberg already implemented.
- The Binance datasets (262 MB) — Vibe-Trading already covers Binance among 29 sources.
- The 13 hand-written strategies — Vibe-Trading has 478 Alpha Zoo factors plus a
  strategy development manager with IC/Sharpe decay.

## Founder rules that must survive the transfer

These are **rules, not code**, and they are the reason the parent project's conclusions
can be trusted:

1. **Leverage is forbidden, permanently.** The founder's directive: leverage is the
   graveyard of investors. Any leverage config must default to `1.0` and require an
   explicit, separate decision to change.
2. **Live trading has a hard stop** until the founder says GO — and passing tests does
   not constitute GO.
3. **A result counts only if it clears the pre-registered gate.** No post-hoc threshold.
4. **Money and time first, statistics small.** Reports open with what the result means
   in dollars and years, not with a t-statistic.
5. **Missing data is `null`, never a plausible-looking number.**
6. **Survivorship caveat on every small-cap figure**: coins that fell to zero are absent
   from 2020-2026 data, so any small-cap result is an upper bound.

---

## Suggested next steps (founder decides)

1. Read `docs/founder/FINAL_REPORT.md` — the honest verdict, in money and time.
2. Read `docs/founder/gates/EDGE_DISTANCE.md` — the eight-gate ladder that decides
   whether a strategy is worth attention.
3. Read `docs/founder/knowledge/12-strategy-templates.md` — which archetypes are worth
   testing in Vibe-Trading's engine, with measured parameters.
4. Decide whether Jev becomes a real provider here (needs a LangChain ChatModel
   implementation on top of `jev_adapter.py`) or stays a research tool.
5. Carry the founder rules into Vibe-Trading's own canon as documentation.
