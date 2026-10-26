"""Read-only audit probes; every HTTP response here is a TEST FIXTURE.

No provider calls, config writes, .env edits, trade orders, or process changes.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(r"C:\Projects\jev-vibe")
OUT = Path(__file__).resolve().parent / "integration-probes.json"
sys.path.insert(0, str(ROOT / "agent"))

import httpx
from jev_module import fallback, providers, routes
from jev_module.judge import JevClient
from jev_module.providers import Provider, ProvidersConfig

findings = {}

# Isolated in-memory registry; existing file contents are never changed.
p1 = Provider(name="one", label="One", base_url="https://audit.invalid/api", model="one-model", tier="free", enabled=True, order=0)
p2 = Provider(name="two", label="Two", base_url="https://audit.invalid/api", model="two-model", tier="paid", enabled=False, order=7, transport="decisions")
config = ProvidersConfig(version="audit", providers=[p1, p2], fallback_order=["one", "two"])
with patch.object(providers, "_config", config), patch.object(providers, "_providers_by_name", {"one": p1, "two": p2}), patch.object(fallback, "_load_state", return_value={"quarantine": {}, "last_test_results": {}}):
    state = fallback.get_fallback_status()
    findings["status_hides_disabled_provider"] = {
        "configured": [p.name for p in config.providers],
        "returned": [p["name"] for p in state["providers"]],
        "missing_metadata": [k for k in ("base_url", "model", "api_key_env", "transport", "order") if k not in state["providers"][0]],
    }

    async def test_patch_semantics():
        capture = []
        req = routes.ProviderRequest(name="two", api_key_env="AUDIT_KEY_NAME")
        with patch.object(routes, "update_provider", side_effect=lambda obj: capture.append(obj)):
            await routes.create_or_update_provider(req)
        after = capture[0]
        return {"before_enabled": p2.enabled, "after_enabled": after.enabled,
                "before_order": p2.order, "after_order": after.order,
                "transport_field_editable": "transport" in routes.ProviderRequest.model_fields}
    findings["partial_update_changes_omitted_fields"] = asyncio.run(test_patch_semantics())

async def malformed_response_probe():
    requests_seen = []
    fixture = {"model": "audit-fixture", "answers": {
        "direction": {"type": "choice", "choice": "not-in-options", "probabilities": {"up": 0.8, "down": 0.8}, "confidence": 1.2}},
        "usage": {"cost": 0.123456}}
    def handler(request):
        requests_seen.append(str(request.url))
        return httpx.Response(200, json=fixture)
    p = Provider(name="fixture", label="Fixture", base_url="https://audit.invalid/api", model="audit-fixture", tier="paid", transport="decisions")
    client = JevClient(p)
    client._client = httpx.AsyncClient(base_url=p.base_url, transport=httpx.MockTransport(handler))
    try:
        result = await client.judge("AUDIT TEST FIXTURE ONLY", {"direction": {"type": "choice", "criteria": {"up": "up", "down": "down"}}})
        return {"fixture_only": True, "rejected": False, "choice": result.choice,
                "probability_sum": sum(result.probabilities.values()), "confidence": result.confidence,
                "reported_cost": result.cost_usd, "fixture_usage_cost": fixture["usage"]["cost"],
                "url": requests_seen}
    except Exception as exc:
        return {"fixture_only": True, "rejected": True, "error_type": type(exc).__name__, "error": str(exc)}
    finally:
        await client.close()

findings["response_validation_and_cost"] = asyncio.run(malformed_response_probe())
findings["scope"] = "Read-only probes, httpx.MockTransport fixtures, no external HTTP and no trading."
OUT.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(findings, ensure_ascii=False, indent=2))
print("AUDIT_PROBE_OUTPUT", OUT)
