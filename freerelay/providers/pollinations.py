"""
FreeRelay — Pollinations Provider
===================================
Anonymous tier (no API key needed). Chat completions endpoint lives at
/openai/v1/chat/completions — the /openai prefix is mandatory.
Public model: openai-fast (GPT-OSS 20B on OVH, tools supported).
"""

from __future__ import annotations

from freerelay.providers.openai_compat import OpenAICompatibleProvider


class PollinationsProvider(OpenAICompatibleProvider):
    """Pollinations anonymous-access provider."""

    name = "pollinations"
    base_url = "https://text.pollinations.ai/openai/v1"
    supported_features = {"streaming", "tools"}
    _default_model = "openai-fast"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        # Anonymous — no Authorization header required
        return {"Content-Type": "application/json"}
