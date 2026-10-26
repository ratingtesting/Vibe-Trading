# JEV — что реализовано (полный реестр)

> Составлено 2026-10-23 из кода и знаний старого проекта `jev-trading-engine`
> и нового клона `jev-vibe` (ветка founder-transfer). Цель: единый файл, чтобы
> никто не спрашивал «а что у нас есть по джеву» и не изобретал заново.

## 1. Суть Jev

Jev — дешёвый ИИ-судья: на вопрос с закрытым меню вариантов отвечает
**выбором + вероятностями + уверенностью** (Choice/Score/Noul), а не текстом.
Цена на OpenRouter `typesafe/jev-1.14`: **$0.042 за 1M входных токенов**
(≈ $0.00002 за один вызов). Массовые прогоны — бесплатно (CPU), Jev — только
судейство на финальных кандидатах.

## 2. Транспортеры (старый проект, `src/core/`, TypeScript)

| Файл | Строк | Что делает |
|---|---|---|
| `judge-jev.ts` | 246 | Прямой клиент TypeSafe Jev (System One) — базовый транспорт |
| `judge-jev-http.ts` | 211 | Универсальный HTTP-клиент на ЛЮБОГО провайдера из реестра |
| `judge-jev-mcp.ts` | 182 | MCP-транспорт (ключи jevai.org, префикс `jev_`) |
| `judge-jev-zen.ts` | 162 | OpenCode Zen /systemone — прямой клиент без локального сервера |
| `judge-jev-opencode.ts` | 147 | Локальный сервер OpenCode (RPC) |
| `judge-jev-cached.ts` | 161 | Дисковый кэш + честный отказ для исследовательских прогонов |
| `jev-providers.ts` | 154 | **Реестр транспортов** — единственный источник правды для панели и бота |
| `judge-fallback.ts` | 103 | Provider-fallback с карантином упавшего на 10 минут |
| `judge.ts` | 128 | Реализации судьи; НЕТ дефолтной модели (поправка D) |
| `judge-sources.ts` | 225 | Слой решений («никакого переключения на self» — правило Петра) |

Цепочка отказоустойчивости: выбранный → остальные бесплатные → OpenRouter
последним (`providerChain` + `ProviderFallbackJudge`).

## 3. Инструменты/инфраструктура

- `~/bin/jev-route` — free-first каскад (Zen jev-1.13-free 12с → платный TypeSafe), одна строка JSON: `source, chosen, probabilities, confidence, cost_usd, latency_ms, receipt`.
- `~/bin/jevrouter`, `~/bin/jev-metrics` — сырой CLI и метрики; журнал решений `C:\Projects\jevrouter\.jevrouter\decisions\*.json`.
- MCP-сервер `jevrouter` (`serve-mcp` → `jev_route` + `jev_capabilities`); в конфиге Hermes включён во всех профилях, но в живой сессии подхватывается нестабильно (известный дефект 18.10.2026).
- Source repo: `C:\Projects\jevrouter` (commit e11084c).

## 4. Знания (документы старого проекта)

- `knowledge/08-criteria-for-jev.md` — критерии использования Jev.
- `knowledge/13-jev-probabilities.md` — работа с вероятностями.
- `PHASE_G_JEV_PROTOCOL_REPORT.md` — Jev-overlay НЕ добавил ценности (честный ноль).
- `PHASE_P1_JEV_CALIBRATION.md` + `research/results/p1-live-calibration.json` — калибровка на 59 живых ответах: **ECE 0.51 — НЕ откалиброван**; вероятности нельзя брать напрямую, нужен маппинг; Kelly-сайзинг закрыт до ECE ≤ 0.10.
- `STRATEGIST_HANDOFF_MEASUREMENT_INSTRUMENT.md` §9 — план подключения Jev к движку.

## 5. В новом проекте `jev-vibe` (ветка founder-transfer)

| Файл | Строк | Что делает |
|---|---|---|
| `wiki/founder/jev_judge.py` | ~140 | Python-судья: регим-вопросы кандидату через `jev-route` (bash-подпроцесс; git-bash резолвится явно — WSL-bash перехватывает). Живой тест: SOLUSDT p=0.67, бесплатно. |
| `wiki/founder/jev_ask.sh` | 11 | Обёртка: аргументы через файлы (обход экранирования кавычек). |
| `wiki/founder/two_level_verdict.py` | ~200 | Применяет двухуровневую планку + Jev-регим-чек на выживших. |

Живые вызовы: 480+ решений в журнале; провайдер `openrouter:~typesafe/jev-latest` (платный тир) и `jev-1.13-free` (бесплатный тир, жив 23.10.2026).

## 6. Ограничения (честно)

1. **Калибровка не пройдена**: ECE 0.51 (норма ≤ 0.10). Вероятности Jev — регим-чек, НЕ размер позиции.
2. Бесплатный тир по IP нестабилен (403 FreeTierError из-за подмены заголовка x-opencode-session); из Hermes-терминала free жив.
3. MCP `jevroute` включён глобально, но не коннектится в каждой сессии — надёжнее CLI `jev-route`.
4. OPENCODE_API_KEY истёк (401); 8933 free tier — 403 по IP.
