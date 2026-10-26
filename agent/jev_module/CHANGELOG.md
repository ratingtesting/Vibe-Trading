# Changelog

All notable changes to the JEV Module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-23

### Added
- **Provider Registry** (`providers.py`, `providers.json`)
  - Configuration schema for JEV providers
  - Support for free (OpenCode Zen) and paid (OpenRouter Typesafe) tiers
  - API key via environment variable name (not value)
  - Enabled/disabled toggle and priority ordering

- **HTTP Client** (`judge.py`)
  - Async httpx-based client for JEV `/v1/systemone` endpoint
  - Structured `JudgmentResult` with choice, probabilities, confidence, cost, latency
  - Configurable timeout per request

- **Fallback Chain** (`fallback.py`)
  - Sequential provider trial in configured order
  - 10-minute quarantine for failed providers
  - Persistent state in `state.json`
  - Test endpoint with automatic quarantine on failure

- **REST API** (`routes.py`)
  - `GET /jev/providers` — list all providers
  - `GET /jev/status` — fallback chain status with quarantine/test results
  - `PUT /jev/order` — update fallback order
  - `POST /jev/provider` — add/update provider
  - `DELETE /jev/provider/{name}` — remove provider
  - `POST /jev/test` — test specific provider
  - `POST /jev/judge` — execute judgment via fallback chain
  - `POST /jev/quarantine/{name}/clear` — manually clear quarantine

- **Frontend** (`frontend/src/components/settings/JevSettings.tsx`, `frontend/src/pages/Jev.tsx`)
  - Provider table with fallback order controls (arrow up/down)
  - Tier badges (Free/Paid)
  - Enable/disable toggles
  - API key environment variable input
  - Test button with loading state and result display
  - Last test status indicators
  - Add/Delete provider dialogs
  - Visual fallback order summary

- **Integration**
  - Single-line router inclusion in `api_server.py`
  - Navigation sidebar entry with Brain icon
  - Route at `/jev` with lazy loading

### Technical Details
- **No core engine modifications** — only router inclusion
- **Clean architecture** — separated concerns (config, client, fallback, routes)
- **State persistence** — quarantine and test results survive restarts
- **Type safety** — Pydantic models for all request/response
- **Error handling** — proper HTTP status codes and error messages

### Providers Included by Default
1. **opencode-zen** (Free) — `https://opencode.ai/zen/v1`, model `jev-1.13-free`
2. **openrouter-typesafe** (Paid) — `https://openrouter.ai/api/v1`, model `typesafe/jev-1.14`, requires `TYPESAFE_API_KEY`

### Files Created
```
agent/jev_module/
├── __init__.py
├── providers.py
├── providers.json
├── judge.py
├── fallback.py
├── routes.py
├── state.json
├── README.md
└── CHANGELOG.md
```

### Frontend Files Created
```
frontend/src/
├── components/settings/JevSettings.tsx
└── pages/Jev.tsx
```

### Frontend Files Modified
- `src/components/layout/navigation.ts` — added JEV nav item
- `src/router.tsx` — added /jev route
- `src/lib/api.ts` — added JEV API client functions