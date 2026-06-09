"""
FreeRelay — Ollama Cloud Provider
====================================
Free plan: 1 concurrent model, GPU-time quota. Many catalog models require
subscription; only Free-confirmed models should be used.
Frontier reasoning models can take 30–90s — timeout bumped to 120s.

Get a free API key at https://ollama.com (sign in, Settings → API Keys).
"""

from __future__ import annotations

import httpx

from freerelay.core.models.openai import ChatCompletionRequest, ChatCompletionResponse
from freerelay.providers.base import ProviderError, RateLimitError
from freerelay.providers.openai_compat import OpenAICompatibleProvider


class OllamaCloudProvider(OpenAICompatibleProvider):
    """Ollama Cloud free-tier provider."""

    name = "ollama_cloud"
    base_url = "https://ollama.com/v1"
    supported_features = {"streaming"}
    _default_model = "llama3.1:8b"

    async def complete(
        self, request: ChatCompletionRequest, api_key: str
    ) -> ChatCompletionResponse:
        payload = self.strip_unsupported_fields(request)
        payload["model"] = self._map_model(payload.get("model"))  # type: ignore[arg-type]
        payload.pop("stream", None)

        try:
            resp = await self.http_client.post(
                f"{self.base_url}/chat/completions",
                headers=self._build_headers(api_key),
                json=payload,
                timeout=120.0,
            )
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"Ollama Cloud timeout: {e}", provider_name=self.name
            )

        if resp.status_code == 429:
            raise RateLimitError(provider_name=self.name)
        if resp.status_code == 403:
            raise ProviderError(
                "Ollama Cloud: model requires subscription",
                status_code=403,
                provider_name=self.name,
            )
        if resp.status_code >= 400:
            raise ProviderError(
                message=resp.text[:300],
                status_code=resp.status_code,
                provider_name=self.name,
            )
        return ChatCompletionResponse.model_validate(resp.json())
