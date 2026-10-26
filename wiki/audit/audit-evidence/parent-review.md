# Проверка перехода Jev-Vibe: родительский аудит

Дата: 2026-10-24. Версия: C:/Projects/jev-vibe @ 1bc9f43cb25f3cf099f9476cb873e7dcac75278c, ветка founder-transfer. Это промежуточное доказательство для итогового отчёта: математическая часть проверяется отдельным read-only аудитором.

## Что проверено фактически

- База Vibe-Trading @ 11cff3f3a2d89605c89148b03dcc2dd0fcfb60db; изменение ядра agent/backtest, agent/src/quantlib, agent/src/providers между базой и HEAD отсутствует по git diff --name-only. Собственные исследовательские обвязки находятся в wiki/founder, Jev-модуль в agent/jev_module.
- Новый Git origin всё ещё HKUDS/Vibe-Trading, а не собственный репозиторий. Новое имя/публикация своего форка не оформлены. Публикация старого репозитория в прошлой истории была подтверждена; текущее удалённое состояние GitHub без веб-проверки не утверждается.
- Старый локальный HEAD 0103b76ce4ede1fd095bd4161ab88201279951b8 равен локальному origin/main (0/0). Это сравнение локальных refs, не свежая проверка удалённого сервера.
- Новый Python пакет: vibe-trading-ai 0.1.18, frontend React 19 + Vite + TypeScript. Новый продукт всё ещё отображается как Vibe-Trading.
- В новой сборке 12 языков, по 2176 листовых ключей в каждой локали; missing/extra отсутствуют. В Jev-компоненте при этом остались нетранслируемые строки Free/Paid/Close, подсказка на русском на всех языках и сообщения ошибок на английском.
- 141 тест CryptoEngine/DSR-библиотеки/каузальности прошли, exit 0. 46 i18n тестов прошли, exit 0. TypeScript tsc -b прошёл, exit 0. Production frontend build создал dist и завершил сборку по сохранённому stdout; метаданные exit потеряны при таймауте программного параллельного вызова, поэтому exit для build не выдумывается.
- Старые тесты: 524 всего, 517 passed, 5 failed, 2 skipped, exit 1. Все пять отказов tests/unified.test.ts зависят от незапущенной старой панели localhost:8800. Тесты не изменялись для прохождения.
- Отдельных тестов нового agent/jev_module или JevSettings в трекнутых тестовых файлах не найдено.
- API :8899 и frontend :5899 были выключены; подняты тем же CLI и npm/Vite способом, без торговли. Readiness /jev/status и / возвращают 200.
- Правильный Pickle найден из текущего pickle-runtime.json: API :60893, в нём личная статья пользователя и системные Pickle Search. Control+t не создал вкладку; использована пустая системная tooling-вкладка, личная статья не перезаписана. /jev проверен через observe/extract и локальный снимок экрана. Шестерёнка открыла форму; отмена закрыла её без сохранения. Расширенное evaluate требовало одобрения и не выполнено; это не скрывается.
- В UI GET /runs возвращает []; наши сканы из wiki/founder не импортированы в историю панели. Founder/BTC-конфигуратор в frontend/src/pages отсутствует.

## Находки и конкретные решения

| Уровень | Файл:строка | Находка | Решение | Объём |
|---|---|---|---|---|
| CRITICAL | agent/jev_module/judge.py:150–166 | Принимает неизвестный choice, сумму вероятностей 1.6 и confidence 1.2; комиссия всегда фиксированная, не usage.cost | Валидировать все Choice/Score/Noul, диапазоны, все question IDs; ошибки -> NO_TRADE; учитывать реальный usage, общий бюджет | M |
| CRITICAL | agent/jev_module/routes.py:32,151,191 | Роутер не подключён к штатным require_auth / require_settings_write_auth; URL и имя переменной ключа задаются произвольно | Подключить существующие зависимости доступа; проверять разрешённые адреса и схемы, изолировать ключи, закрыть SSRF/перенаправление секретов | M |
| MAJOR | agent/api_server.py:318–319 | Jev подключён как API-роутер, не как обязательный этап торгового решения | Адаптер judgment -> policy -> independent risk, shadow comparison до влияния на сделки | L |
| MAJOR | agent/jev_module/providers.json | Бесплатный провайдер использует внешний локальный мост 8933; независимость всего пути от внешнего окружения не доказана | Прямой systemone-клиент или проектный управляемый адаптер, собственный lifecycle/config; прямой Decisions для OpenRouter; тест без внешнего моста | M |
| MAJOR | frontend/src/components/settings/JevSettings.tsx:417–442; agent/jev_module/fallback.py:208–225 | Редактор очищает URL/model, order при сохранении меняется; статус скрывает disabled и не отдаёт метаданные | Полная DTO провайдера, неизменяемый ID, сохранение только явно заданных полей; порядок отдельной полной перестановкой | M |
| MAJOR | agent/jev_module/routes.py:50–51,159–163 | Partial update сбрасывает omitted enabled=false -> true и order=7 -> 0 | model_dump(exclude_unset=True), отдельная валидация создания; регрессионные тесты на частичные обновления | S |
| MAJOR | frontend/src/pages/Reports.tsx:40; wiki/founder/results-page.html | История наших сканов отсутствует; отдельный HTML устарел и не содержит настраиваемой BTC-стратегии | Единый реестр run_id + версий + параметров + комиссий + данных; экран истории и сравнения baseline/overlay | L |
| MAJOR | wiki/founder/build_results_page.py:35–46,76–118 | Две кривые отдельно нормализуются и накладываются без общей шкалы; показывается старый JSON, размеры окна предупреждений неточны | Кривые из неизменяемых equity CSV, общая долларовая/логарифмическая шкала от $100, даты, drawdown, статус проверки; без пересчёта при рендеринге | M |
| MAJOR | graphify-out/graph.json | Граф содержит 49003 узла/127421 ребро/1046 сообществ, но не содержит JevClient/JevSettings и не имеет GRAPH_REPORT.md | Обновить граф по изменённым файлам, реальная семантика документов, manifest/проверка целостности; не представлять структурную обработку Markdown как LLM-перевод | M |
| MAJOR | wiki/founder/README.md и JEV_IMPLEMENTATION.md | Описывают прототип и старые пути docs/founder; заявленные результаты не соответствуют текущему состоянию | Синхронизировать README/STATUS/реестр интеграции по фактическому состоянию; не обнулять историю после исправлений | S |

## Воспроизводимые малые пробы, без провайдерных HTTP-запросов

integration_probes.py использует httpx.MockTransport и in-memory конфиг. Это ТЕСТОВЫЕ фикстуры, не ответы Jev:
1. Отключённый провайдер исчезает из get_fallback_status.
2. Частичная правка имени переменной ключа меняет enabled=false на true, order=7 на 0.
3. malformed answer с unknown choice / probabilities sum=1.6 / confidence=1.2 принимается без отказа.
4. usage.cost=0.123456 в фикстуре игнорируется, reported_cost остаётся 0.0000144.

Доказательства: integration-probes.json, integration-evidence.json, tests.json, inventory.json, pickle-ui-trace.json, pickle-edit-form.json, pickle-jev-page.txt, frontend_build.log.

## Числа не являются доказательством прибыли

В sample-run-metrics.json для TSMOM-vol10-452 (BTC) реальные fills=204 и fee>0: движок торгует. Но position_adjustment=hold, rebalance_executed_fills=0, dropped_target_adjustment_count=1268 — риск-режим не исполняет изменения веса как заявлено. Этот недостаток должен быть исправлен и затронутые бэктесты перепроверены, а не назван нормальным предупреждением.

Окончательные вердикты по DSR, портфелю и BTC-учёту дополняются после независимой проверки. До этого прежние PASS/FAIL и BTC-доходность не считаются принятыми результатами.
