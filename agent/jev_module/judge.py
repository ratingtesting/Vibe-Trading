"""JEV Module - HTTP Client for JEV Providers.

Calls the JEV API endpoint with a question and candidate, and returns a
strictly validated judgment with probabilities.

Validation policy (declared here so callers can rely on it):

* every requested question id must be answered;
* ``choice`` must be one of the option ids supplied in the request;
* every probability must be a finite number in [0, 1];
* probabilities must sum to 1 within ``PROBABILITY_SUM_TOLERANCE``;
* ``confidence`` must be a finite number in [0, 1];
* any violation raises :class:`JevClientError`, which the fallback chain
  treats as a provider failure. A malformed judgment never becomes a
  tradeable signal.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .providers import Provider

# Allowed probability sum deviation before the answer is rejected.
PROBABILITY_SUM_TOLERANCE = 0.05


@dataclass
class JudgmentResult:
    """Result of a JEV judgment call."""
    choice: str
    probabilities: dict[str, float]
    confidence: float
    cost_usd: float
    latency_ms: int
    provider_name: str
    raw_response: dict[str, Any]
    cost_source: str = "unavailable"
    model: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


class JevClientError(Exception):
    """Error calling JEV provider."""
    pass


def _as_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise JevClientError(f"JEV answer has non-numeric {label}: {value!r}") from exc
    if not math.isfinite(result):
        raise JevClientError(f"JEV answer has non-finite {label}: {value!r}")
    return result


def validate_answer(
    answer: dict[str, Any],
    question_spec: dict[str, Any],
    question_id: str,
) -> tuple[str, dict[str, float], float]:
    """Validate one raw answer against the question that produced it.

    Returns (choice, probabilities, confidence) or raises JevClientError.
    """
    if not isinstance(answer, dict):
        raise JevClientError(f"JEV answer for '{question_id}' is not an object")

    choice = answer.get("choice")
    if not isinstance(choice, str) or not choice.strip():
        raise JevClientError(f"JEV answer for '{question_id}' has no usable 'choice'")

    criteria = question_spec.get("criteria") or {}
    allowed = set(criteria) if isinstance(criteria, dict) else set()
    if allowed and choice not in allowed:
        raise JevClientError(
            f"JEV answer for '{question_id}' has choice '{choice}' outside the offered options"
        )

    raw_probabilities = answer.get("probabilities")
    if not isinstance(raw_probabilities, dict) or not raw_probabilities:
        raise JevClientError(f"JEV answer for '{question_id}' has no 'probabilities'")

    probabilities: dict[str, float] = {}
    for key, value in raw_probabilities.items():
        if allowed and key not in allowed:
            raise JevClientError(
                f"JEV answer for '{question_id}' has probability for unknown option '{key}'"
            )
        number = _as_float(value, f"probability '{key}'")
        if number < 0.0 or number > 1.0:
            raise JevClientError(
                f"JEV answer for '{question_id}' has probability {number} outside [0, 1]"
            )
        probabilities[key] = number

    total = sum(probabilities.values())
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
        raise JevClientError(
            f"JEV answer for '{question_id}' probabilities sum to {total:.3f}, expected 1.0"
        )

    confidence = _as_float(answer.get("confidence", 0.0), "confidence")
    if confidence < 0.0 or confidence > 1.0:
        raise JevClientError(
            f"JEV answer for '{question_id}' has confidence {confidence} outside [0, 1]"
        )

    return choice, probabilities, confidence


def _extract_usage(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage")
    return usage if isinstance(usage, dict) else {}


def _compute_cost(provider: Provider, usage: dict[str, Any]) -> tuple[float, str]:
    """Compute the request cost from real usage when the provider reports it."""
    price_per_million = provider.price_per_million_input_tokens
    if not price_per_million:
        return 0.0, "unavailable"
    prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
    total_tokens = usage.get("total_tokens")
    tokens = prompt_tokens if prompt_tokens is not None else total_tokens
    if tokens is None:
        return 0.0, "unavailable"
    try:
        cost = float(tokens) / 1_000_000.0 * float(price_per_million)
    except (TypeError, ValueError):
        return 0.0, "unavailable"
    return round(cost, 10), "usage"


class JevClient:
    """HTTP client for calling JEV providers."""

    def __init__(self, provider: Provider, timeout: float = 30.0):
        self.provider = provider
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Cloudflare cuts the default httpx user-agent (Err 1010); mimic the
                # working zen client's UA.
                "User-Agent": "opencode/2.0.15",
            }
            api_key = self.provider.get_api_key()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.provider.base_url.rstrip("/"),
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    async def _post_chat_completions(
        self,
        client: httpx.AsyncClient,
        state: str,
        questions: dict[str, dict[str, Any]],
        model: str,
    ) -> httpx.Response:
        """OpenRouter chat/completions transport.

        Kept for providers that expose a plain chat endpoint. The Typesafe
        Jev model on OpenRouter is a Decisions model and uses the
        ``decisions`` transport instead.
        """
        raise JevClientError(
            "chat/completions transport is not available for this provider; "
            "use transport='decisions' or 'systemone'"
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def judge(
        self,
        state: str,
        questions: dict[str, dict[str, Any]],
        model: str | None = None,
    ) -> JudgmentResult:
        """Call JEV provider with a judgment request.

        Args:
            state: Compact factual state as text
            questions: Mapping of question_id -> question spec
            model: Override model (defaults to provider's model)

        Returns:
            JudgmentResult with choice, probabilities, confidence, cost, latency
        """
        client = await self._get_client()
        model = model or self.provider.model

        payload = {
            "state": state,
            "model": model,
            "questions": questions,
        }

        start = time.perf_counter()
        try:
            if self.provider.transport == "decisions":
                # OpenRouter native Decisions route: same body shape as
                # systemone ({state, model, questions}), different URL.
                response = await client.post("/alpha/decisions", json=payload)
            else:
                # base_url already ends in /v1 (opencode zen bridge); systemone
                # sits next to it.
                response = await client.post("/systemone", json=payload)
        except httpx.HTTPError as exc:
            raise JevClientError(f"JEV HTTP call failed: {exc}") from exc

        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.status_code >= 400:
            raise JevClientError(
                f"JEV returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise JevClientError(f"JEV returned non-JSON: {response.text[:200]}") from exc

        if "error" in data:
            raise JevClientError(f"JEV rejected request: {data['error']}")

        # JEV returns {answers: {question_id: {choice, probabilities, confidence}}}
        answers = data.get("answers", {})
        if not isinstance(answers, dict) or not answers:
            raise JevClientError("JEV response missing 'answers' field")

        missing = [qid for qid in questions if qid not in answers]
        if missing:
            raise JevClientError(f"JEV response missing answers for: {', '.join(missing)}")

        # Every requested question is validated; the first one carries the signal.
        validated: dict[str, tuple[str, dict[str, float], float]] = {}
        for qid, spec in questions.items():
            validated[qid] = validate_answer(answers[qid], spec, qid)

        question_id = next(iter(questions))
        choice, probabilities, confidence = validated[question_id]

        usage = _extract_usage(data)
        cost_usd, cost_source = _compute_cost(self.provider, usage)

        return JudgmentResult(
            choice=choice,
            probabilities=probabilities,
            confidence=confidence,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            provider_name=self.provider.name,
            raw_response=data,
            cost_source=cost_source,
            model=model,
            usage=usage,
        )


async def call_provider(
    provider: Provider,
    state: str,
    questions: dict[str, dict[str, Any]],
    model: str | None = None,
    timeout: float = 30.0,
) -> JudgmentResult:
    """Convenience function to call a provider once."""
    client = JevClient(provider, timeout=timeout)
    try:
        return await client.judge(state, questions, model)
    finally:
        await client.close()