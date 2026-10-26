"""Tests for the JEV module: answer validation, cost accounting, safe merges.

All provider calls are mocked; no network access happens in this file.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from jev_module.judge import (  # noqa: E402
    JevClientError,
    PROBABILITY_SUM_TOLERANCE,
    validate_answer,
)
from jev_module.providers import Provider  # noqa: E402

QUESTIONS = {
    "direction": {
        "type": "choice",
        "instructions": "Which outcome is more likely?",
        "criteria": {"up": "higher", "down": "lower"},
    }
}


def _answer(**overrides):
    answer = {"choice": "up", "probabilities": {"up": 0.7, "down": 0.3}, "confidence": 0.8}
    answer.update(overrides)
    return answer


def test_valid_answer_is_accepted():
    choice, probabilities, confidence = validate_answer(
        _answer(), QUESTIONS["direction"], "direction"
    )
    assert choice == "up"
    assert probabilities == {"up": 0.7, "down": 0.3}
    assert confidence == 0.8


def test_unknown_choice_is_rejected():
    with pytest.raises(JevClientError):
        validate_answer(_answer(choice="sideways"), QUESTIONS["direction"], "direction")


def test_probability_sum_outside_tolerance_is_rejected():
    with pytest.raises(JevClientError):
        validate_answer(
            _answer(probabilities={"up": 0.9, "down": 0.7}),
            QUESTIONS["direction"],
            "direction",
        )


def test_probability_sum_within_tolerance_is_accepted():
    up = 1.0 - PROBABILITY_SUM_TOLERANCE / 2
    validate_answer(
        _answer(probabilities={"up": up, "down": PROBABILITY_SUM_TOLERANCE / 2}),
        QUESTIONS["direction"],
        "direction",
    )


def test_probability_out_of_range_is_rejected():
    with pytest.raises(JevClientError):
        validate_answer(
            _answer(probabilities={"up": 1.4, "down": -0.4}),
            QUESTIONS["direction"],
            "direction",
        )


def test_confidence_out_of_range_is_rejected():
    with pytest.raises(JevClientError):
        validate_answer(_answer(confidence=1.2), QUESTIONS["direction"], "direction")


def test_probability_for_unknown_option_is_rejected():
    with pytest.raises(JevClientError):
        validate_answer(
            _answer(probabilities={"up": 0.5, "down": 0.3, "flat": 0.2}),
            QUESTIONS["direction"],
            "direction",
        )


def test_provider_rejects_credential_in_base_url():
    with pytest.raises(ValueError):
        Provider(
            name="p",
            label="p",
            base_url="https://user:secret@example.com/v1",
            model="m",
            tier="paid",
        )


def test_provider_rejects_non_http_scheme():
    with pytest.raises(ValueError):
        Provider(
            name="p",
            label="p",
            base_url="file:///etc/passwd",
            model="m",
            tier="free",
        )


def test_provider_rejects_secret_as_api_key_env():
    with pytest.raises(ValueError):
        Provider(
            name="p",
            label="p",
            base_url="https://example.com/v1",
            model="m",
            tier="paid",
            api_key_env="sk-real-secret-value",
        )


def test_provider_rejects_unknown_transport():
    with pytest.raises(ValueError):
        Provider(
            name="p",
            label="p",
            base_url="https://example.com/v1",
            model="m",
            tier="paid",
            transport="telepathy",
        )


def test_merge_keeps_omitted_fields(tmp_path, monkeypatch):
    """A partial upsert must not wipe stored values (A10 regression)."""
    from jev_module import providers as providers_module
    from jev_module import routes as routes_module

    stored = providers_module.Provider(
        name="demo",
        label="Demo",
        base_url="https://example.com/v1",
        model="demo-model",
        api_key_env="DEMO_KEY",
        tier="paid",
        transport="decisions",
        enabled=False,
        order=7,
    )
    saved = {}

    monkeypatch.setattr(routes_module, "get_provider", lambda name: stored)
    monkeypatch.setattr(routes_module, "update_provider", lambda provider: saved.update(provider=provider))

    request = routes_module.ProviderRequest(name="demo", api_key_env="NEW_KEY")
    merged = asyncio.run(routes_module.create_or_update_provider(request))

    assert merged.base_url == "https://example.com/v1"
    assert merged.model == "demo-model"
    assert merged.api_key_env == "NEW_KEY"
    assert merged.enabled is False
    assert merged.order == 7
    assert merged.transport == "decisions"
    assert saved["provider"].base_url == "https://example.com/v1"
