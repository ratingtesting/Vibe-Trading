"""JEV Module - FastAPI Routes.

REST endpoints for managing JEV providers and executing judgments.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from src.api.security import require_local_or_auth, require_settings_write_auth

from .fallback import (
    get_fallback_status,
    judge_with_fallback,
    quarantine_provider,
    clear_quarantine,
    test_provider,
)
from .providers import (
    Provider,
    add_provider,
    get_provider,
    get_providers,
    load_config,
    persist_config,
    reorder_providers,
    remove_provider,
    update_provider,
)

router = APIRouter(prefix="/jev", tags=["JEV"])


# --- Request/Response Models ---


class ProviderRequest(BaseModel):
    """Request to add/update a provider.

    Fields beyond ``name`` are optional: omitted (None) fields keep their
    current values on an existing provider (merge semantics).
    """
    name: str = Field(..., min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=128)
    base_url: str | None = Field(default=None, min_length=1)
    model: str | None = Field(default=None, min_length=1)
    api_key_env: str | None = Field(default=None, max_length=128)
    tier: str | None = Field(default=None, pattern="^(free|paid)$")
    transport: str | None = Field(default=None, pattern="^(systemone|decisions)$")
    enabled: bool | None = None
    order: int | None = None
    price_per_million_input_tokens: float | None = Field(default=None, ge=0.0)


class ProviderResponse(BaseModel):
    """Provider response."""
    name: str
    label: str
    base_url: str
    model: str
    api_key_env: str
    tier: str
    transport: str
    enabled: bool
    order: int
    price_per_million_input_tokens: float | None = None


class OrderRequest(BaseModel):
    """Request to update fallback order."""
    order: list[str] = Field(..., min_length=1)


class TestRequest(BaseModel):
    """Request to test a provider."""
    name: str = Field(..., min_length=1)


class JudgeRequest(BaseModel):
    """Request to execute a judgment."""
    state: str = Field(..., min_length=1)
    questions: dict[str, dict[str, Any]] = Field(..., min_length=1)
    model: str | None = None
    timeout: float = Field(default=30.0, ge=1.0, le=120.0)


class JudgeResponse(BaseModel):
    """Judgment response."""
    choice: str
    probabilities: dict[str, float]
    confidence: float
    cost_usd: float
    latency_ms: int
    provider_name: str
    raw_response: dict[str, Any]
    cost_source: str = "unavailable"
    model: str = ""


class StatusResponse(BaseModel):
    """Status response."""
    fallback_order: list[str]
    providers: list[dict[str, Any]]


# --- Helper Functions ---


def _provider_to_response(p: Provider) -> ProviderResponse:
    return ProviderResponse(
        name=p.name,
        label=p.label,
        base_url=p.base_url,
        model=p.model,
        api_key_env=p.api_key_env,
        tier=p.tier,
        transport=p.transport,
        enabled=p.enabled,
        order=p.order,
        price_per_million_input_tokens=p.price_per_million_input_tokens,
    )


# --- Routes ---


@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    _auth: None = Depends(require_local_or_auth),
) -> list[ProviderResponse]:
    """List all configured providers."""
    providers = get_providers()
    return [_provider_to_response(p) for p in providers]


@router.get("/status", response_model=StatusResponse)
async def get_status(
    _auth: None = Depends(require_local_or_auth),
) -> StatusResponse:
    """Get fallback chain status with quarantine and test results."""
    status_data = get_fallback_status()
    return StatusResponse(**status_data)


@router.put("/order", response_model=StatusResponse)
async def update_order(
    request: OrderRequest,
    _auth: None = Depends(require_settings_write_auth),
) -> StatusResponse:
    """Update fallback order (array of provider names)."""
    # Validate all names exist
    config = load_config()
    known_names = {p.name for p in config.providers}
    for name in request.order:
        if name not in known_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown provider name: {name}",
            )
    missing = known_names - set(request.order)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Fallback order must list every provider exactly once; "
                f"missing: {', '.join(sorted(missing))}"
            ),
        )

    reorder_providers(request.order)
    return await get_status()


@router.post("/provider", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_provider(
    request: ProviderRequest,
    _auth: None = Depends(require_settings_write_auth),
) -> ProviderResponse:
    """Add a new provider or merge-update an existing one.

    Merge semantics: fields omitted by the client (None) keep their current
    values, so a status-only payload (toggle enabled / api_key_env) never
    wipes base_url or model.
    """
    # exclude_unset: a field the client did not send must never overwrite the
    # stored value (an omitted ``enabled`` must not silently enable a
    # disabled provider, and an omitted ``order`` must not reset it).
    payload = request.model_dump(exclude_unset=True)
    existing = get_provider(payload["name"])
    if existing:
        updates = {k: v for k, v in payload.items() if v is not None}
        try:
            merged = existing.model_copy(update=updates)
            # Re-validate: model_copy skips field validators.
            merged = Provider(**merged.model_dump())
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid provider: {exc.errors()[0]['msg'] if exc.errors() else 'validation failed'}",
            ) from exc
        update_provider(merged)
        return _provider_to_response(merged)
    missing_required = [
        field for field in ("label", "base_url", "model", "tier") if not payload.get(field)
    ]
    if missing_required:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"New provider requires: {', '.join(missing_required)}",
        )
    try:
        provider = Provider(
            **{
                key: value
                for key, value in payload.items()
                if value is not None
            }
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider: {exc.errors()[0]['msg'] if exc.errors() else 'validation failed'}",
        ) from exc
    add_provider(provider)
    return _provider_to_response(provider)


@router.delete("/provider/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    name: str,
    _auth: None = Depends(require_settings_write_auth),
) -> None:
    """Remove a provider."""
    if not get_provider(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{name}' not found",
        )
    remove_provider(name)


@router.post("/test", response_model=dict[str, Any])
async def test_provider_endpoint(
    request: TestRequest,
    _auth: None = Depends(require_local_or_auth),
) -> dict[str, Any]:
    """Test a specific provider with a sample judgment."""
    try:
        result = await test_provider(request.name)
        return result
    except Exception as exc:
        return {"success": False, "error": str(exc), "quarantined": True}


@router.post("/judge", response_model=JudgeResponse)
async def execute_judgment(
    request: JudgeRequest,
    _auth: None = Depends(require_local_or_auth),
) -> JudgeResponse:
    """Execute a judgment using the fallback chain."""
    try:
        result = await judge_with_fallback(
            state=request.state,
            questions=request.questions,
            model=request.model,
            timeout=request.timeout,
        )
        return JudgeResponse(
            choice=result.choice,
            probabilities=result.probabilities,
            confidence=result.confidence,
            cost_usd=result.cost_usd,
            latency_ms=result.latency_ms,
            provider_name=result.provider_name,
            raw_response=result.raw_response,
            cost_source=result.cost_source,
            model=result.model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post("/quarantine/{name}/clear", status_code=status.HTTP_204_NO_CONTENT)
async def clear_provider_quarantine(
    name: str,
    _auth: None = Depends(require_settings_write_auth),
) -> None:
    """Manually clear quarantine for a provider."""
    if not get_provider(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{name}' not found",
        )
    clear_quarantine(name)