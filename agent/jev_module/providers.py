"""JEV Module - Providers Registry.

Loads provider configuration from providers.json and exposes
a clean interface for the fallback chain.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

# The judge resolves keys lazily via env-var NAMES; make sure the repo's .env
# files are loaded (CWD .env + agent/.env) before anything asks for a key.
load_dotenv()
_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE.parent.parent / "agent" / ".env", override=True)

# Environment variable names are the only thing the UI may reference; a
# provider may never carry a literal secret.
ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALLOWED_TRANSPORTS = ("systemone", "decisions")
ALLOWED_URL_SCHEMES = ("http", "https")


class Provider(BaseModel):
    """Single JEV provider configuration."""
    name: str
    label: str
    base_url: str
    model: str
    api_key_env: str = ""
    tier: str  # "free" | "paid"
    transport: str = "systemone"  # "systemone" | "decisions"
    enabled: bool = True
    order: int = 0
    # Published input price per million tokens, used to price real usage.
    price_per_million_input_tokens: float | None = None

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in ALLOWED_URL_SCHEMES:
            raise ValueError("base_url must use http or https")
        if not parsed.hostname:
            raise ValueError("base_url must contain a host")
        if parsed.username or parsed.password:
            raise ValueError("base_url must not embed credentials")
        return value.rstrip("/")

    @field_validator("api_key_env")
    @classmethod
    def _check_api_key_env(cls, value: str) -> str:
        if value and not ENV_NAME_PATTERN.match(value):
            raise ValueError("api_key_env must be an environment variable NAME, not a secret")
        return value

    @field_validator("transport")
    @classmethod
    def _check_transport(cls, value: str) -> str:
        if value not in ALLOWED_TRANSPORTS:
            raise ValueError(f"transport must be one of {', '.join(ALLOWED_TRANSPORTS)}")
        return value

    @field_validator("tier")
    @classmethod
    def _check_tier(cls, value: str) -> str:
        if value not in ("free", "paid"):
            raise ValueError("tier must be 'free' or 'paid'")
        return value

    def get_api_key(self) -> str | None:
        """Get API key from environment variable if configured."""
        if not self.api_key_env:
            return None
        return os.environ.get(self.api_key_env)


class ProvidersConfig(BaseModel):
    """Full providers configuration."""
    version: str
    providers: list[Provider]
    fallback_order: list[str]


# Module-level cache
_config: ProvidersConfig | None = None
_providers_by_name: dict[str, Provider] | None = None
_config_mtime: float | None = None


def load_config(config_path: Path | None = None) -> ProvidersConfig:
    """Load providers configuration from JSON file."""
    global _config, _providers_by_name, _config_mtime

    if config_path is None:
        config_path = Path(__file__).parent / "providers.json"

    # Reload when the file changed on disk: the panel edits providers.json
    # outside this process, so a stale cache would hide the user's changes.
    try:
        mtime = config_path.stat().st_mtime
    except OSError:
        mtime = None
    if _config is not None and mtime is not None and mtime == _config_mtime:
        return _config

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _config = ProvidersConfig(**data)
    _providers_by_name = {p.name: p for p in _config.providers}
    _config_mtime = mtime
    return _config


def get_providers() -> list[Provider]:
    """Get all providers sorted by order."""
    config = load_config()
    return sorted(config.providers, key=lambda p: p.order)


def get_enabled_providers() -> list[Provider]:
    """Get enabled providers sorted by fallback order."""
    config = load_config()
    enabled = [p for p in config.providers if p.enabled]
    # Sort by fallback_order first, then by order field
    order_map = {name: idx for idx, name in enumerate(config.fallback_order)}
    return sorted(enabled, key=lambda p: order_map.get(p.name, p.order))


def get_provider(name: str) -> Provider | None:
    """Get a single provider by name."""
    config = load_config()
    return _providers_by_name.get(name)


def update_provider(provider: Provider) -> None:
    """Update a provider in memory and persist to JSON."""
    global _config, _providers_by_name, _config_mtime
    load_config()

    for i, p in enumerate(_config.providers):
        if p.name == provider.name:
            _config.providers[i] = provider
            _providers_by_name[provider.name] = provider
            break
    else:
        _config.providers.append(provider)
        _providers_by_name[provider.name] = provider

    persist_config()


def add_provider(provider: Provider) -> None:
    """Add a new provider."""
    update_provider(provider)


def remove_provider(name: str) -> bool:
    """Remove a provider by name."""
    global _config, _providers_by_name, _config_mtime
    load_config()

    _config.providers = [p for p in _config.providers if p.name != name]
    if name in _providers_by_name:
        del _providers_by_name[name]

    # Also remove from fallback_order
    _config.fallback_order = [n for n in _config.fallback_order if n != name]

    persist_config()
    return True


def reorder_providers(new_order: list[str]) -> None:
    """Update fallback order (array of provider names)."""
    global _config, _config_mtime
    load_config()
    _config.fallback_order = new_order
    persist_config()


def persist_config(config_path: Path | None = None) -> None:
    """Persist current config to JSON file."""
    global _config, _config_mtime
    if _config is None:
        return

    if config_path is None:
        config_path = Path(__file__).parent / "providers.json"

    data = {
        "version": _config.version,
        "providers": [p.model_dump() for p in _config.providers],
        "fallback_order": _config.fallback_order,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    try:
        _config_mtime = config_path.stat().st_mtime
    except OSError:
        _config_mtime = None


def get_fallback_chain() -> list[Provider]:
    """Get the fallback chain in order."""
    return get_enabled_providers()