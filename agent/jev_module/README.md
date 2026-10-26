# JEV Module

AI Judge Engine for Vibe-Trading — fallback chain of JEV (Typesafe System One) providers for typed judgments with probabilities.

## Architecture

```
agent/jev_module/
├── __init__.py       # Exports router, version
├── providers.py      # Configuration registry (providers.json)
├── providers.json    # Provider definitions
├── judge.py          # HTTP client for JEV endpoints
├── fallback.py       # Fallback chain with 10-min quarantine
├── routes.py         # FastAPI REST endpoints at /jev/*
├── state.json        # Runtime state (quarantine, test results)
├── README.md         # This file
└── CHANGELOG.md      # Version history
```

## Providers Configuration

Providers are defined in `providers.json`:

```json
{
  "version": "1.0.0",
  "providers": [
    {
      "name": "opencode-zen",
      "label": "OpenCode Zen (Free)",
      "base_url": "https://opencode.ai/zen/v1",
      "model": "jev-1.13-free",
      "api_key_env": "",
      "tier": "free",
      "enabled": true,
      "order": 0
    },
    {
      "name": "openrouter-typesafe",
      "label": "OpenRouter (Typesafe/jev-1.14)",
      "base_url": "https://openrouter.ai/api/v1",
      "model": "typesafe/jev-1.14",
      "api_key_env": "TYPESAFE_API_KEY",
      "tier": "paid",
      "enabled": true,
      "order": 1
    }
  ],
  "fallback_order": ["opencode-zen", "openrouter-typesafe"]
}
```

### Provider Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique identifier |
| `label` | string | Display name |
| `base_url` | string | API base URL |
| `model` | string | Model identifier |
| `api_key_env` | string | Environment variable name for API key (empty for keyless) |
| `tier` | "free" \| "paid" | Provider tier |
| `enabled` | boolean | Whether provider is active |
| `order` | integer | Fallback priority (lower = higher priority) |

## How Fallback Works

1. **Order**: Providers are tried in `fallback_order` sequence
2. **Quarantine**: Failed providers are quarantined for 10 minutes
3. **Retry**: After quarantine expires, provider re-enters the chain
4. **State**: Quarantine and test results persisted in `state.json`

## API Endpoints

All endpoints under `/jev/`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/providers` | List all configured providers |
| GET | `/status` | Get fallback chain status (quarantine, test results) |
| PUT | `/order` | Update fallback order (body: `{order: string[]}`) |
| POST | `/provider` | Add or update provider |
| DELETE | `/provider/{name}` | Remove provider |
| POST | `/test` | Test a provider (body: `{name: string}`) |
| POST | `/judge` | Execute judgment via fallback chain |
| POST | `/quarantine/{name}/clear` | Manually clear quarantine |

### Judgment Request

```json
POST /jev/judge
{
  "state": "BTC is trading at $50,000. 30-day return: +5%. Regime: up.",
  "questions": {
    "direction": {
      "type": "choice",
      "instructions": "Which single outcome is more likely?",
      "criteria": {
        "up": "price is higher after 30 days",
        "down": "price is lower after 30 days"
      }
    }
  },
  "model": "jev-1.13-free",
  "timeout": 30.0
}
```

### Judgment Response

```json
{
  "choice": "up",
  "probabilities": {"up": 0.72, "down": 0.28},
  "confidence": 0.68,
  "cost_usd": 0.0,
  "latency_ms": 1847,
  "provider_name": "opencode-zen",
  "raw_response": {...}
}
```

## Adding a Provider

1. **Via API**: `POST /jev/provider` with provider JSON
2. **Via Config**: Edit `providers.json` and restart server
3. **Required**: Unique `name`, valid `base_url`, `model`, `tier`

### Example: Add Custom Provider

```bash
curl -X POST http://localhost:8899/jev/provider \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-jev",
    "label": "My JEV Instance",
    "base_url": "https://my-jev.example.com/v1",
    "model": "jev-1.14",
    "api_key_env": "MY_JEV_API_KEY",
    "tier": "paid",
    "enabled": true,
    "order": 2
  }'
```

## Frontend Integration

The `/jev` page provides:
- Provider list with drag-and-drop fallback order (arrow buttons)
- Enable/disable toggle per provider
- API key environment variable input
- Test button with result display
- Last test status badges
- Add/Delete provider actions

## Version

**v1.0.0** — Initial release
- Provider registry with JSON config
- HTTP client with httpx
- Fallback chain with 10-minute quarantine
- FastAPI REST endpoints
- React settings page
- State persistence

## Changelog

See [CHANGELOG.md](CHANGELOG.md)