"""JEV Module - Fallback Chain with Quarantine.

Manages the fallback chain of providers, quarantines failed providers
for 10 minutes, and returns the first successful result.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .judge import JudgmentResult, JevClient, JevClientError, call_provider
from .providers import Provider, get_fallback_chain, get_providers, load_config


# Module-level quarantine state: provider_name -> quarantine_until_timestamp
_quarantine: dict[str, float] = {}

# State file path
_STATE_FILE = Path(__file__).parent / "state.json"


def _load_state() -> dict[str, Any]:
    """Load state from JSON file."""
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"quarantine": {}, "last_test_results": {}}


def _save_state(state: dict[str, Any]) -> None:
    """Save state to JSON file."""
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _sync_quarantine() -> None:
    """Sync in-memory quarantine with persisted state."""
    global _quarantine
    state = _load_state()
    _quarantine = state.get("quarantine", {})


def _persist_quarantine() -> None:
    """Persist quarantine to state file."""
    state = _load_state()
    state["quarantine"] = _quarantine
    _save_state(state)


def is_quarantined(provider_name: str) -> bool:
    """Check if a provider is currently quarantined."""
    _sync_quarantine()
    until = _quarantine.get(provider_name, 0)
    return time.time() < until


def quarantine_provider(provider_name: str, minutes: int = 10) -> None:
    """Quarantine a provider for the given number of minutes."""
    _sync_quarantine()
    _quarantine[provider_name] = time.time() + (minutes * 60)
    _persist_quarantine()


def clear_quarantine(provider_name: str) -> None:
    """Manually clear quarantine for a provider."""
    _sync_quarantine()
    if provider_name in _quarantine:
        del _quarantine[provider_name]
        _persist_quarantine()


def get_quarantine_remaining(provider_name: str) -> int:
    """Get remaining quarantine time in seconds (0 if not quarantined)."""
    _sync_quarantine()
    until = _quarantine.get(provider_name, 0)
    remaining = int(until - time.time())
    return max(0, remaining)


async def judge_with_fallback(
    state: str,
    questions: dict[str, dict[str, Any]],
    model: str | None = None,
    timeout: float = 30.0,
) -> JudgmentResult:
    """Execute judgment with fallback chain.

    Iterates through enabled providers in fallback order, skipping
    quarantined ones. Returns first successful result.

    Args:
        state: Compact factual state as text
        questions: Mapping of question_id -> question spec
        model: Optional model override
        timeout: HTTP timeout per provider

    Returns:
        JudgmentResult from the first successful provider

    Raises:
        JevClientError: If all providers fail or are quarantined
    """
    providers = get_fallback_chain()
    if not providers:
        raise JevClientError("No enabled providers configured")

    errors: list[str] = []

    for provider in providers:
        if is_quarantined(provider.name):
            remaining = get_quarantine_remaining(provider.name)
            errors.append(f"{provider.name}: quarantined for {remaining}s")
            continue

        try:
            result = await call_provider(provider, state, questions, model, timeout)
            # Record successful test
            _record_test_result(provider.name, True, result.latency_ms)
            return result
        except JevClientError as exc:
            errors.append(f"{provider.name}: {exc}")
            quarantine_provider(provider.name, minutes=10)
            _record_test_result(provider.name, False, 0, str(exc))
            continue

    raise JevClientError(f"All providers failed: {'; '.join(errors)}")


async def test_provider(provider_name: str) -> dict[str, Any]:
    """Test a specific provider with a simple judgment.

    Returns test result with success status, latency, and error if any.
    """
    from .providers import get_provider
    provider = get_provider(provider_name)
    if not provider:
        return {"success": False, "error": f"Provider '{provider_name}' not found"}

    if is_quarantined(provider_name):
        return {
            "success": False,
            "error": f"Provider quarantined for {get_quarantine_remaining(provider_name)}s",
            "quarantined": True,
        }

    # Simple test question
    test_state = "Test symbol is trading at $100. Its 30-day return was +5%. Regime: up."
    test_questions = {
        "direction": {
            "type": "choice",
            "instructions": "Which single outcome is more likely?",
            "criteria": {
                "up": "price is higher than today's close after 30 days",
                "down": "price is lower than today's close after 30 days",
            },
        }
    }

    try:
        result = await call_provider(provider, test_state, test_questions, timeout=30.0)
        _record_test_result(provider_name, True, result.latency_ms)
        return {
            "success": True,
            "provider": provider_name,
            "choice": result.choice,
            "probabilities": result.probabilities,
            "confidence": result.confidence,
            "latency_ms": result.latency_ms,
            "cost_usd": result.cost_usd,
        }
    except JevClientError as exc:
        quarantine_provider(provider_name, minutes=10)
        _record_test_result(provider_name, False, 0, str(exc))
        return {"success": False, "error": str(exc), "quarantined": True}


def _record_test_result(
    provider_name: str, success: bool, latency_ms: int, error: str | None = None
) -> None:
    """Record test result in state."""
    state = _load_state()
    results = state.get("last_test_results", {})
    results[provider_name] = {
        "success": success,
        "latency_ms": latency_ms,
        "error": error,
        "timestamp": time.time(),
    }
    state["last_test_results"] = results
    _save_state(state)


def get_last_test_results() -> dict[str, Any]:
    """Get last test results for all providers."""
    state = _load_state()
    return state.get("last_test_results", {})


def get_fallback_status() -> dict[str, Any]:
    """Get status of all providers in fallback chain.

    Disabled providers stay visible: the owner has to be able to see and
    re-enable them. Only the chain order itself reflects enabled providers.
    """
    providers = get_providers()
    test_results = get_last_test_results()

    return {
        "fallback_order": [p.name for p in get_fallback_chain()],
        "providers": [
            {
                "name": p.name,
                "label": p.label,
                "tier": p.tier,
                "base_url": p.base_url,
                "model": p.model,
                "transport": p.transport,
                "api_key_env": p.api_key_env,
                "enabled": p.enabled,
                "order": p.order,
                "quarantined": is_quarantined(p.name),
                "quarantine_remaining_s": get_quarantine_remaining(p.name),
                "last_test": test_results.get(p.name),
            }
            for p in providers
        ],
    }