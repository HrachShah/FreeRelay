"""
FreeRelay — Cerebras Cloud Provider.
Free tier: Llama 3.1 8B/70B, up to 30 RPM.
OpenAI-compatible endpoint.
"""

from __future__ import annotations

from freerelay.providers.openai_compat import OpenAICompatibleProvider


class CerebrasProvider(OpenAICompatibleProvider):
    """Cerebras Cloud inference — extremely fast (wafer-scale chip)."""

    name = "cerebras"
    base_url = "https://api.cerebras.ai/v1"
    supported_features = {"streaming"}
    _default_model = "llama3.1-8b"
