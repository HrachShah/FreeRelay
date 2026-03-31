"""
FreeRelay — OpenRouter Provider (§7.3)
========================================
OpenAI-compatible. Requires extra headers: HTTP-Referer, X-Title.
Free models have :free suffix.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


class OpenRouterProvider(BaseProvider):
    """OpenRouter free-tier provider."""

    name = "openrouter"
    base_url = "https://openrouter.ai/api/v1"
    supported_features = {"streaming", "tools"}

    _default_model = "meta-llama/llama-3.1-8b-instruct:free"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/HrachShah/freerelay",
            "X-Title": "FreeRelay",
        }

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = self.strip_unsupported_fields(request)
        if not payload.get("model"):
            payload["model"] = self._default_model
        payload.pop("stream", None)

        resp = await self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(api_key),
            json=payload,
        )

        if resp.status_code == 429:
            raise RateLimitError(provider_name=self.name)
        if resp.status_code >= 400:
            raise ProviderError(
                message=resp.text[:300],
                status_code=resp.status_code,
                provider_name=self.name,
            )

        return ChatCompletionResponse.model_validate(resp.json())

    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        payload = self.strip_unsupported_fields(request)
        if not payload.get("model"):
            payload["model"] = self._default_model
        payload["stream"] = True

        async with self.http_client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(api_key),
            json=payload,
        ) as resp:
            if resp.status_code == 429:
                raise RateLimitError(provider_name=self.name)
            if resp.status_code >= 400:
                await resp.aread()
                raise ProviderError(
                    message=resp.text[:300],
                    status_code=resp.status_code,
                    provider_name=self.name,
                )
            async for line in resp.aiter_lines():
                if line.strip():
                    yield f"{line}\n\n"

    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        return request.estimate_tokens()
