"""
FreeRelay — Anthropic Provider (Paid)
======================================
Anthropic Claude API (requires paid API key).
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    Message,
    Usage,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


def _openai_to_anthropic(request: ChatCompletionRequest) -> dict[str, object]:
    """Convert OpenAI request to Anthropic format."""
    messages = []

    for msg in request.messages:
        if isinstance(msg.content, str):
            messages.append({"role": msg.role, "content": msg.content})
        else:
            messages.append({"role": msg.role, "content": str(msg.content)})

    payload: dict[str, object] = {
        "model": "claude-3-5-sonnet-20241022",
        "messages": messages,
        "max_tokens": request.max_tokens or 1024,
    }

    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p

    return payload


def _anthropic_to_openai(anthropic_json: dict, model: str) -> ChatCompletionResponse:
    """Convert Anthropic response to OpenAI format."""
    content = anthropic_json.get("content", [])
    text = content[0].get("text", "") if content else ""

    usage = anthropic_json.get("usage", {})

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
        created=int(time.time()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=Message(role="assistant", content=text),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        ),
    )


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider (paid)."""

    name = "anthropic"
    base_url = "https://api.anthropic.com/v1"
    supported_features = {"streaming"}

    _default_model = "claude-3-5-sonnet-20241022"

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = _openai_to_anthropic(request)

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        resp = await self.http_client.post(
            f"{self.base_url}/messages",
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

        return _anthropic_to_openai(resp.json(), self._default_model)

    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        payload = _openai_to_anthropic(request)
        payload["stream"] = True

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with self.http_client.stream(
            "POST",
            f"{self.base_url}/messages",
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
