"""
FreeRelay — OpenCode Provider
================================
Proxies requests through OpenCode Zen API.

OpenCode has two auth modes:
1. Free tier: Models ending in -free (e.g., mimo-v2-pro-free) work
   without any authentication. The API serves these for free.
2. Paid tier: All other models require an OPENCODE_API_KEY.

Model listing also works without auth — the catalog is publicly accessible.

The base URL is configurable via OPENCODE_BASE_URL env var,
defaulting to the public OpenCode Zen API endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


def _is_free_model(model: str) -> bool:
    """Check if a model is in the free tier (ends with -free)."""
    return model.endswith("-free")


def _resolve_model(request: ChatCompletionRequest) -> str:
    """
    Resolve the model name for OpenCode.

    If the request model looks like a raw OpenCode model name
    (contains a dash, e.g., mimo-v2-pro-free), pass it through.
    Otherwise use the request.model as-is.
    """
    model = request.model or ""
    # Strip freerelay/ prefix if present
    if model.startswith("opencode/"):
        model = model[len("opencode/") :]
    return model or "mimo-v2-pro-free"


class OpenCodeProvider(BaseProvider):
    """
    OpenCode Zen API provider.

    Supports both free-tier models (-free suffix, no auth required)
    and paid models (require OPENCODE_API_KEY).
    """

    name = "opencode"
    base_url = "https://opencode.ai/v1"
    supported_features = {"streaming", "tools"}

    _default_model = "mimo-v2-pro-free"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        """Build request headers. Auth header is optional for free models."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = self.strip_unsupported_fields(request)
        payload["model"] = _resolve_model(request) or self._default_model
        payload.pop("stream", None)

        headers = self._build_headers(api_key)

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

        headers = self._build_headers(api_key)

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


async def fetch_opencode_models(api_key: str = "") -> list[dict[str, str]]:
    """
    Fetch the OpenCode model catalog.

    Model listing does NOT require auth — the catalog is publicly accessible.
    If an API key is provided, it's sent in the Authorization header.

    Returns a list of model dicts with id, name, and free flag.
    """
    from freerelay.shared.http_client import get_client

    client = get_client()
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = await client.get(
            "https://opencode.ai/v1/models",
            headers=headers,
        )
        if resp.status_code == 200:
            data = resp.json()
            models_data = data.get("data", data) if isinstance(data, dict) else data
            models = []
            for m in models_data:
                if isinstance(m, dict):
                    model_id = m.get("id", "")
                    models.append(
                        {
                            "id": model_id,
                            "name": m.get("name", model_id),
                            "free": _is_free_model(model_id),
                        }
                    )
            return models
    except httpx.RequestError:
        pass
    except (ValueError, TypeError):
        pass
    except AttributeError:
        pass

    # Fallback: return known free model
    return [
        {
            "id": "mimo-v2-pro-free",
            "name": "MiMo v2 Pro (Free)",
            "free": True,
        }
    ]


def get_known_free_models() -> list[dict[str, str]]:
    """Return known OpenCode free-tier models."""
    return [
        {"id": "mimo-v2-pro-free", "name": "MiMo v2 Pro (Free)"},
    ]
