"""
FreeRelay — Z.ai Provider (GLM / Zhipu AI).
OpenAI-compatible endpoint at https://api.z.ai/api/paas/v4.
Free tier available on new accounts.
"""

from __future__ import annotations

from freerelay.providers.openai_compat import OpenAICompatibleProvider


class ZaiProvider(OpenAICompatibleProvider):
    """Z.ai / Zhipu AI — GLM-4 series models."""

    name = "zai"
    base_url = "https://api.z.ai/api/paas/v4"
    supported_features = {"streaming", "tools", "vision"}
    _default_model = "glm-4-flash"
