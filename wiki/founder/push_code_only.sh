#!/usr/bin/env bash
# Пуш без артефактов прогонов.
#
# ПРОБЛЕМА. В истории репозитория 107 186 файлов артефактов прогонов
# (CSV/JSONL каждого прогона). GitHub отваливается на их упаковке:
# HTTP 408 (таймаут) и "pack-objects died of signal 15" при ~50k объектах.
#
# РЕШЕНИЕ. Отдельная ветка с ОДНИМ коммитом, содержащим только исходники
# (код, тесты, документы, артефакты отчётов) — без каталогов прогонов.
# Локальная история founder-transfer остаётся нетронутой и полной.
#
# Что исключается: wiki/founder/{scan-10k,archetype-scan,freqtrade-scan,
# risk-overlay}/ — это сгенерированные результаты, воспроизводимые скриптами.
set -euo pipefail

REPO=/c/Projects/jev-vibe
cd "$REPO"

BRANCH=code-only
EXCLUDE=(
  "wiki/founder/scan-10k/"
  "wiki/founder/archetype-scan/"
  "wiki/founder/freqtrade-scan/"
  "wiki/founder/risk-overlay/"
  "wiki/founder/last-year/"
  "wiki/founder/candidates-13-5y/runs/"
  "wiki/founder/scan5y/returns/"
  "wiki/founder/scan5y/runs/"
  "wiki/founder/alpha-zoo-results/"
  "wiki/founder/combo-overlay/"
  "wiki/founder/first-backtest/"
  "wiki/founder/gates/"
  "wiki/founder/phases/"
  "wiki/founder/knowledge/"
  "wiki/founder/lessons/"
  "wiki/founder/archetypes/__pycache__/"
)

git checkout --orphan "$BRANCH" 2>/dev/null || true
git rm -rf --cached . >/dev/null 2>&1 || true
rm -rf .git/index

git read-tree --empty
git add -A -- . ':!wiki/founder/scan-10k' ':!wiki/founder/archetype-scan' \
  ':!wiki/founder/freqtrade-scan' ':!wiki/founder/risk-overlay' \
  ':!wiki/founder/last-year' ':!wiki/founder/candidates-13-5y/runs' \
  ':!wiki/founder/scan5y/returns' ':!wiki/founder/scan5y/runs' \
  ':!wiki/founder/alpha-zoo-results' ':!wiki/founder/combo-overlay' \
  ':!wiki/founder/first-backtest' ':!wiki/founder/gates' ':!wiki/founder/phases' \
  ':!wiki/founder/knowledge' ':!wiki/founder/lessons' \
  ':!wiki/founder/archetypes/__pycache__' 2>/dev/null || true

# Добавленные файлы без exclude-путей всё равно могут включать артефакты:
# чистим индекс по списку.
for pattern in "${EXCLUDE[@]}"; do
  git rm -r --cached --ignore-unmatch "$pattern" >/dev/null 2>&1 || true
done

STAGED=$(git diff --cached --name-only | wc -l)
echo "в индексе файлов: $STAGED"

git commit -q -m "feat(jev-vibe): founder research stack — honest DSR, 5-year scan, BTC-kopilka, UI

Squashed snapshot of the founder-transfer work (local history stays intact
in the founder-transfer branch; this branch carries the source only, because
GitHub times out while packing the 107k run-artifact files).

What is in here:
- research_metrics.py — single measurement scale: per-observation Sharpe
  (the one DSR requires), signed t, drawdown as loss magnitude, real
  skew/kurtosis (non-excess), unknown != zero.
- honest_dsr_recheck.py — pool-wide DSR over every run on disk (8174) in one
  per-observation scale. Result: REFERENCE 0, CANDIDATE 0, best DSR 0.4244.
  The earlier 'single PASS, DSR=0.9998' was an annualised-Sharpe artefact.
- selfcheck_no_candidates.py — the owner's challenge: pool completeness,
  Sharpe reproduced by two independent routes, and which condition kills
  each row (t passes for 66, DD for 2945, DSR for 0).
- scan5y.py — 5-year scan (2021-10-20..2026-10-19, 1826 daily bars),
  34992 runs = 88 variants x 3 risk modes x 144 pairs, annualised return
  (prod(1+r))^(365/n)-1, rebalance sizing so the vol/drawdown overlays
  actually resize the book.
- kopilka_5y.py — the owner's BTC-kopilka with the full account split:
  BTC in units, BTC in USD, asset in USD, cash, combined total.
- candidates_13_5y.py — the 13 candidates over 5 years, tables only.
- report_5y.py — tabular report generator (no prose sections).
- extend_loader_config.py — the loader config listed 47 symbols while 144
  were on disk, so pairs were silently skipped.
- Founder.tsx — BTC-kopilka configurator fixed (duplicate interface broke
  the build; parameters were read from results[] instead of sensitivity[]).
- agent/tests/test_research_metrics_regression.py (12) and
  agent/tests/test_kopilka_5y_regression.py (4) — regressions for the three
  measurement defects and the kopilka zeroing bug."

echo "--- пуш ---"
git push --force fork "$BRANCH:$BRANCH"
echo "PUSH_OK"
