"""
FreeRelay — OpenAICompatibleProvider base class.

All providers that speak the OpenAI chat completions wire format inherit
from this instead of duplicating the same complete/stream/estimate_tokens
boilerplate.  Subclasses only need to declare class-level attributes and
optionally override ``_build_headers`` or ``_map_model``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


class OpenAICompatibleProvider(BaseProvider):
    """
    Reusable base for OpenAI-compatible chat completion providers.

    Subclasses must define:
      - ``name``: provider identifier string
      - ``base_url``: upstream API root (no trailing slash)
      - ``_default_model``: fallback model name
      - ``supported_features``: set of feature strings

    Optional overrides:
      - ``_build_headers(api_key)``: return the auth header dict
      - ``_map_model(model_str)``: normalize the model name for this provider
    """

    name: str = ""
    base_url: str = ""
    supported_features: set[str] = {"streaming"}
    _default_model: str = ""

    def _build_headers(self, api_key: str) -> dict[str, str]:
        """Return HTTP headers. Override for non-Bearer auth."""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _map_model(self, model: str | None) -> str:
        """Normalize the model name. Override to remap model strings."""
        return model or self._default_model

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = self.strip_unsupported_fields(request)
        payload["model"] = self._map_model(payload.get("model"))  # type: ignore[arg-type]
        payload.pop("stream", None)

        resp = await self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers=self._build_headers(api_key),
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
        payload["model"] = self._map_model(payload.get("model"))  # type: ignore[arg-type]
        payload["stream"] = True

        async with self.http_client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._build_headers(api_key),
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
