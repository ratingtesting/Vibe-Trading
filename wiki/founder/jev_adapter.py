"""Typesafe Jev (System One) provider for Vibe-Trading.

# Почему Jev

Jev — LLM-судья от Typesafe System One, который отвечает **типизированными суждениями**
(Choice / Score / Noul) с **вероятностями** на компактный state. Это не «ещё один чат-LLM»:
это семантический движок, заточенный под вопросы вида «up / down / flat» или
«supports_candidate / against_candidate / unable_to_evaluate».

# Чего ожидать от Jev (измерено 2026-10-19 в родительском проекте jev-trading-engine)

- Средняя вероятность P(up) ~ 0.38 при базе 0.49, Brier 0.504, **ECE 0.51** — вероятности
  **не откалиброваны**. Их нельзя использовать для Kelly-сайзинга напрямую.
- Ответы приходят за ~1.8-3.2 сек (платный тир Typesafe через OpenRouter).
- Endpoint: `POST /v1/systemone` с payload вида:

    {
      "state": "<compact factual state as text>",
      "model": "jev-1.13.0",
      "questions": {
        "direction": {
          "type": "choice",
          "instructions": "Which way does price go next?",
          "criteria": {"up": "...", "down": "...", "flat": "..."}
        }
      }
    }

  Ответ: `{"model": "...", "answers": {"direction": {"type": "choice", "choice": "up",
  "probabilities": {"up": 0.8, "down": 0.2}, "confidence": 0.7}}}`

# Как подключить в Vibe-Trading

Vibe-Trading работает через LangChain и провайдеры из `llm_providers.json`. У Jev
**не OpenAI-совместимый endpoint**, поэтому прямой перенацеливание `base_url` не
работает. Два пути:

## Путь A (рекомендуемый): через MCP

У Typesafe есть MCP-обёртка для Jev. Подключаем как обычный MCP-инструмент — Vibe-Trading
умеет MCP из коробки (см. `agent/mcp_server.py`). Jev-судья будет **инструментом** агента,
а не заменой основного LLM. Это правильно: Jev отвечает **суждениями**, а не чатом.

## Путь B: через кастомный провайдер (этот файл)

Собственный провайдер, который заворачивает HTTP-вызов Jev в интерфейс LangChain
ChatModel. Для этого нужно:

1. Заполнить `CUSTOM_PROVIDER_*` env-переменные (Jev не даёт OpenAI-compatible endpoint,
   поэтому нужна прокси-прослойка, см. ниже).
2. Или использовать через OpenRouter (у Jev есть модель `typesafe/jev-1.14-20261014`
   и роутер `jev-route` в родительском проекте).

**Файл НЕ регистрирует себя в фабрике `build_llm()` автоматически** — это прототип
документации. Для продакшена требуется написать реальный LangChain ChatModel класс,
что выходит за рамки переноса документации.

# История (из родительского проекта)

- 2026-10-11: ECE 0.44, Brier 0.467 vs no-info 0.249, 386 directional answers, 5-bar horizon.
- 2026-10-19: ECE 0.51, Brier 0.504 vs no-info 0.250, **skill vs base −1.02**, 59 live answers
  over 10 symbols × 6 dates, 30-day horizon. Reliability: Jev says 2.3% and the market rises
  52.8% of the time; says 94% and it rises 40.9%.

**Вывод: вероятности Jev НЕЛЬЗЯ использовать для размера позиции напрямую.**
Порог `ECE > 0.10` в родительском проекте автоматически отключает Kelly-сайзинг.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-1.13.0"
REQUEST_TIMEOUT_SECONDS = 30.0


class JevSystemOneError(RuntimeError):
    """The Jev /v1/systemone endpoint returned an error or refused to answer."""


def call_systemone(
    *,
    state: str,
    questions: dict[str, dict[str, Any]],
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Call the Typesafe Jev ``/v1/systemone`` endpoint.

    Args:
        state: Compact factual state as text. Must be small — the model judges,
            not calculates. See ``docs/founder/knowledge/08-criteria-for-jev.md``
            for the formulation guide.
        questions: Mapping of question id → question spec. Each spec has
            ``type`` (``choice`` | ``score`` | ``noul``), optional
            ``instructions``, and for ``choice`` a ``criteria`` dict of
            variant id → human description (at least 2 variants).
        model: Jev model id, e.g. ``jev-1.13.0``.
        api_key: Typesafe API key. Reads ``TYPESAFE_API_KEY`` when omitted.
        base_url: Override for the base URL (for the Typesafe proxy or OpenRouter).
        timeout_seconds: HTTP timeout. Jev typically answers in 1.8-3.2 s on the paid tier.

    Returns:
        Parsed JSON response from Jev.

    Raises:
        JevSystemOneError: When the HTTP call fails or the endpoint returns an error.
    """
    key = api_key or os.environ.get("TYPESAFE_API_KEY") or ""
    if not key:
        raise JevSystemOneError("TYPESAFE_API_KEY is not set; Jev cannot be called.")
    url = (base_url or os.environ.get("TYPESAFE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    body = {"state": state, "model": model, "questions": questions}

    try:
        response = httpx.post(
            f"{url}/v1/systemone",
            json=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise JevSystemOneError(f"Jev HTTP call failed: {exc}") from exc

    if response.status_code >= 400:
        raise JevSystemOneError(
            f"Jev returned HTTP {response.status_code}: {response.text[:300]}"
        )
    payload: dict[str, Any] = response.json()
    if "error" in payload:
        raise JevSystemOneError(f"Jev rejected the request: {payload['error']}")
    return payload


def ask_direction(
    *,
    symbol: str,
    price: float,
    drift_30d_pct: float,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    base_url: str | None = None,
    horizon_days: int = 30,
) -> dict[str, Any]:
    """Ask Jev which way ``symbol`` goes over the next ``horizon_days``.

    This is the minimal, honest form: a plain factual state, three answer
    variants, no arithmetic criteria. Arithmetic criteria made Jev answer
    ``"neutral"`` in 98% of calls in the parent project — the fix was to
    reduce the state to a few natural-language facts (see
    ``docs/founder/knowledge/08-criteria-for-jev.md``).

    Returns:
        Jev's parsed response. ``response["answers"]["direction"]["probabilities"]``
        holds the class probabilities; ``response["answers"]["direction"]["choice"]``
        the argmax choice.
    """
    regime = "up" if drift_30d_pct > 3 else "down" if drift_30d_pct < -3 else "flat"
    state = (
        f"{symbol} is trading at ${price:.2f}. "
        f"Its return over the last 30 days was {drift_30d_pct:.2f} percent. "
        f"Regime: {regime}."
    )
    questions = {
        "direction": {
            "type": "choice",
            "instructions": "Which single outcome is more likely?",
            "criteria": {
                "up": f"price is higher than today's close after {horizon_days} days",
                "down": f"price is lower than today's close after {horizon_days} days",
            },
        }
    }
    return call_systemone(
        state=state,
        questions=questions,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )


def extract_probabilities(payload: dict[str, Any], question_id: str = "direction") -> dict[str, float]:
    """Pull class probabilities out of a Jev response.

    Probabilities can arrive in two places: a normal decision has them at the
    top level, while a low-confidence ``no_decision`` keeps the model's answer
    inside ``raw_jev.answers.<question_id>``. Discarding the second form would
    discard valid data — the parent project made exactly that mistake.
    """
    answers = payload.get("answers") or {}
    answer = answers.get(question_id) or {}
    probabilities = answer.get("probabilities")
    if not probabilities:
        raw = payload.get("raw_jev") or {}
        nested = (raw.get("answers") or {}).get(question_id) or {}
        probabilities = nested.get("probabilities") or {}
    return {str(k): float(v) for k, v in (probabilities or {}).items()}
