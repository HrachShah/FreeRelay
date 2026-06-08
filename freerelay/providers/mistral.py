"""
FreeRelay — Mistral AI Provider
=================================
OpenAI-compatible. Very limited free tier.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from freerelay.core.models.embeddings import EmbeddingRequest, EmbeddingResponse
from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


class MistralProvider(BaseProvider):
    """Mistral AI free-tier provider — also supports embeddings."""

    name = "mistral"
    base_url = "https://api.mistral.ai/v1"
    supported_features = {"streaming", "embeddings"}

    _default_model = "mistral-small-latest"

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

    async def embed(
        self,
        request: EmbeddingRequest,
        api_key: str,
    ) -> EmbeddingResponse:
        texts = request.inputs_as_strings()
        model = request.model if "mistral" in request.model else "mistral-embed"

        payload: dict[str, object] = {"input": texts, "model": model}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        resp = await self.http_client.post(
            f"{self.base_url}/embeddings",
            headers=headers,
            json=payload,
        )

        if resp.status_code == 429:
            raise RateLimitError(provider_name=self.name)
        if resp.status_code >= 400:
            raise ProviderError(resp.text[:300], status_code=resp.status_code, provider_name=self.name)

        data = resp.json()
        vectors = [item["embedding"] for item in data.get("data", [])]
        usage = data.get("usage", {})
        return EmbeddingResponse.from_vectors(
            vectors, model=model, prompt_tokens=usage.get("prompt_tokens", 0)
        )
