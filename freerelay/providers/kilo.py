"""
FreeRelay — Kilo AI Gateway Provider
======================================
OpenAI-compatible aggregator. Keyless access allowed for :free routes,
rate-limited to ~200 req/hr per IP. The Authorization header is omitted for
anonymous access. Free prompts/outputs are logged for training (Kilo's terms).
"""

from __future__ import annotations

from freerelay.providers.openai_compat import OpenAICompatibleProvider


class KiloProvider(OpenAICompatibleProvider):
    """Kilo AI Gateway — anonymous :free-route provider."""

    name = "kilo"
    base_url = "https://api.kilo.ai/api/gateway/v1"
    supported_features = {"streaming", "tools"}
    _default_model = "meta-llama/llama-4-scout:free"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key and api_key != "anon":
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _map_model(self, model: str | None) -> str:
        """Ensure :free suffix is present for anonymous access."""
        m = model or self._default_model
        if m and not m.endswith(":free") and "/" in m:
            m = f"{m}:free"
        return m or self._default_model
