"""
FreeRelay — OpenCode Provider
================================
Proxies requests through the OpenCode platform, supporting both:
- OpenCode Zen: Curated multi-model proxy (Claude, GPT, Gemini, etc.)
- OpenCode Go: Kimi, GLM, MiniMax coding models

Auth via OPENCODE_API_KEY or OPENCODE_ZEN_API_KEY env var.
API endpoint: https://opencode.ai/auth

OpenCode is OpenAI-compatible, so this provider translates minimally.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError

# Model catalogs
_ZEN_MODELS = {
    "opencode-claude-sonnet": "claude-sonnet-4-20250514",
    "opencode-claude-haiku": "claude-3-5-haiku-20241022",
    "opencode-gpt-4o": "gpt-4o",
    "opencode-gpt-4o-mini": "gpt-4o-mini",
    "opencode-gemini-flash": "gemini-2.0-flash",
    "opencode-gemini-pro": "gemini-1.5-pro",
}

_GO_MODELS = {
    "opencode-kimi-k2": "kimi-k2",
    "opencode-glm-4": "glm-4",
    "opencode-minimax-01": "minimax-01",
}

_ALL_MODELS = {**_ZEN_MODELS, **_GO_MODELS}


def _resolve_model(request: ChatCompletionRequest) -> str:
    """Map FreeRelay model ID to OpenCode upstream model name."""
    model = request.model or ""
    if model in _ALL_MODELS:
        return _ALL_MODELS[model]
    # Pass through if it looks like a raw model name
    if "/" in model or "-" in model:
        return model
    return "claude-sonnet-4-20250514"


class OpenCodeZenProvider(BaseProvider):
    """OpenCode Zen — curated multi-model proxy."""

    name = "opencode-zen"
    base_url = "https://opencode.ai/v1"
    supported_features = {"streaming", "tools", "vision"}

    _default_model = "opencode-claude-sonnet"

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = self.strip_unsupported_fields(request)
        payload["model"] = _resolve_model(request) or self._default_model
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
        payload["model"] = _resolve_model(request) or self._default_model
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


class OpenCodeGoProvider(BaseProvider):
    """OpenCode Go — Kimi, GLM, MiniMax coding models."""

    name = "opencode-go"
    base_url = "https://opencode.ai/v1"
    supported_features = {"streaming", "tools"}

    _default_model = "opencode-kimi-k2"

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = self.strip_unsupported_fields(request)
        payload["model"] = _resolve_model(request) or self._default_model
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
        payload["model"] = _resolve_model(request) or self._default_model
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


def get_opencode_models() -> list[dict[str, str]]:
    """Return all available OpenCode models for listing."""
    models = []
    for freerelay_id, upstream_id in _ALL_MODELS.items():
        catalog = "zen" if freerelay_id in _ZEN_MODELS else "go"
        models.append(
            {
                "id": f"freerelay/{freerelay_id}",
                "name": f"OpenCode {catalog.title()}: {upstream_id}",
                "provider": "opencode",
                "catalog": catalog,
                "upstream": upstream_id,
            }
        )
    return models
