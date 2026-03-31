"""
FreeRelay — Together AI Provider (§7.4)
=========================================
OpenAI-compatible. Good for batch tasks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


class TogetherProvider(BaseProvider):
    """Together AI free-tier provider."""

    name = "together"
    base_url = "https://api.together.xyz/v1"
    supported_features = {"streaming"}

    _default_model = "meta-llama/Llama-3.1-8B-Instruct-Turbo"

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = self.strip_unsupported_fields(request)
        if not payload.get("model"):
            payload["model"] = self._default_model
        payload.pop("stream", None)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        resp = await self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
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

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with self.http_client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=headers,
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
