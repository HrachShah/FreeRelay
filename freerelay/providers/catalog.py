"""
FreeRelay — Data-driven provider catalog loader.

Reads freerelay/config/providers.yaml and creates OpenAICompatibleProvider
instances on the fly. No new Python class needed per provider — just add a
YAML entry.

Providers with a matching hand-written class (groq, google, etc.) are skipped
by the catalog loader; the hand-written class takes precedence.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from freerelay.providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("freerelay.catalog")

_CATALOG_PATH = Path(__file__).parent.parent / "config" / "providers.yaml"

# Provider IDs that have hand-written classes — catalog skips them
_HAND_WRITTEN = {
    "groq", "google_ai", "openrouter", "together", "mistral",
    "nvidia", "cerebras", "cohere", "github_models", "huggingface",
    "ollama_cloud", "z_ai", "cloudflare_workers_ai", "pollinations",
    "llm7", "kilo", "blackbox", "openai", "anthropic",
    "opencode", "codex",
}


def _make_provider(entry: dict) -> type[OpenAICompatibleProvider] | None:
    """Dynamically create an OpenAICompatibleProvider subclass from a catalog entry."""
    provider_id = entry.get("id", "")
    if not provider_id:
        return None

    if provider_id in _HAND_WRITTEN:
        logger.debug("Skipping catalog entry %r — hand-written class exists", provider_id)
        return None

    base_url = entry.get("base_url", "")
    default_model = entry.get("default_model", "")
    auth_header = entry.get("auth_header", "Bearer")
    features = {"streaming"}

    class _DynamicProvider(OpenAICompatibleProvider):
        name = provider_id
        supported_features = features

        def _build_headers(self, api_key: str) -> dict[str, str]:
            if auth_header == "none":
                return {"Content-Type": "application/json"}
            return {auth_header: api_key, "Content-Type": "application/json"}

        def _map_model(self, model: str | None) -> str:
            return model or default_model

    _DynamicProvider.__name__ = f"{provider_id.title().replace('_', '')}Provider"
    _DynamicProvider.base_url = base_url  # type: ignore[attr-defined]
    _DynamicProvider._default_model = default_model  # type: ignore[attr-defined]
    return _DynamicProvider


def load_catalog(path: Path = _CATALOG_PATH) -> list[dict]:
    """Load and return raw catalog entries from YAML."""
    if not path.exists():
        logger.warning("Provider catalog not found at %s", path)
        return []
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("providers", [])


def build_catalog_providers(
    path: Path = _CATALOG_PATH,
) -> list[tuple[type[OpenAICompatibleProvider], str, int | None, dict | None, str]]:
    """
    Return a list of (ProviderClass, api_key, daily_limit, rate_limits, tier)
    tuples ready to pass to RoutingEngine.register_provider().

    API keys are read from env vars named in entry["env_key"].
    Permanently-free providers use api_key="anon".
    Providers without a key AND without permanently_free=true are skipped.
    """
    entries = load_catalog(path)
    result = []

    for entry in entries:
        provider_id = entry.get("id", "")
        if provider_id in _HAND_WRITTEN:
            continue

        cls = _make_provider(entry)
        if cls is None:
            continue

        permanently_free = entry.get("permanently_free", False)
        env_key = entry.get("env_key", "")
        api_key = "anon" if permanently_free else os.environ.get(env_key, "")

        if not api_key:
            logger.debug("Skipping %r — no API key configured (%s)", provider_id, env_key)
            continue

        rl = entry.get("rate_limits")
        rate_limits = dict(rl) if rl else None
        tier = entry.get("tier", "free")

        result.append((cls, api_key, None, rate_limits, tier))
        logger.info("Catalog provider registered: %s (tier=%s)", provider_id, tier)

    return result


if __name__ == "__main__":
    # ponytail: self-check — lists what would be registered given current env
    entries = load_catalog()
    print(f"Catalog: {len(entries)} entries")
    registered = build_catalog_providers()
    print(f"Would register: {len(registered)} catalog providers")
    for cls, key, _, rl, tier in registered:
        print(f"  {cls.name:<25} tier={tier}  key={'anon' if key == 'anon' else key[:8] + '...'}")
