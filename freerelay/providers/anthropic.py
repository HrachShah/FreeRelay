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


def _extract_text(content: str | list | None) -> str:
    """Extract plain text from OpenAI content field."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if text:
                    parts.append(text)
            elif hasattr(part, "text") and part.text:
                parts.append(part.text)
        return " ".join(parts)
    return ""


def _openai_to_anthropic(
    request: ChatCompletionRequest,
) -> dict[str, object]:
    """Convert OpenAI request to Anthropic format."""
    messages = []
    system_parts: list[str] = []

    for msg in request.messages:
        text = _extract_text(msg.content)
        if msg.role == "system":
            system_parts.append(text)
        else:
            messages.append({"role": msg.role, "content": text})

    model = request.model or "claude-3-5-sonnet-20241022"

    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
        "max_tokens": request.max_tokens or 1024,
    }

    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.tools:
        tools = []
        for tool in request.tools:
            tools.append(
                {
                    "name": tool.function.name,
                    "description": tool.function.description or "",
                    "input_schema": tool.function.parameters
                    or {"type": "object", "properties": {}},
                }
            )
        payload["tools"] = tools

    return payload


def _anthropic_to_openai(anthropic_json: dict, model: str) -> ChatCompletionResponse:
    """Convert Anthropic response to OpenAI format."""
    content = anthropic_json.get("content", [])
    text = ""
    tool_calls = None

    for block in content:
        if isinstance(block, dict):
            if block.get("type") == "text":
                text += block.get("text", "")
            elif block.get("type") == "tool_use":
                from freerelay.core.models.openai import FunctionCall, ToolCall

                if tool_calls is None:
                    tool_calls = []
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", f"call_{uuid.uuid4().hex[:12]}"),
                        function=FunctionCall(
                            name=block.get("name", ""),
                            arguments=json.dumps(block.get("input", {})),
                        ),
                    )
                )

    usage = anthropic_json.get("usage", {})

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
        created=int(time.time()),
        model=model,
        choices=[
            Choice(
                index=0,
                message=Message(
                    role="assistant",
                    content=text if text else None,
                    tool_calls=tool_calls,
                ),
                finish_reason="stop",
            )
        ],
        usage=Usage(
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=(usage.get("input_tokens", 0) + usage.get("output_tokens", 0)),
        ),
    )


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider (paid)."""

    name = "anthropic"
    base_url = "https://api.anthropic.com/v1"
    supported_features = {"streaming", "tools"}

    _default_model = "claude-3-5-sonnet-20241022"

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        payload = _openai_to_anthropic(request)
        model = request.model or self._default_model

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

        return _anthropic_to_openai(resp.json(), model)

    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        payload = _openai_to_anthropic(request)
        payload["stream"] = True
        model = request.model or self._default_model

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
                if line.startswith("data: "):
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        yield "data: [DONE]\n\n"
                        continue
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("delta", {})
                        text = delta.get("text", "")
                        if text:
                            openai_chunk = {
                                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": {"content": text},
                                        "finish_reason": None,
                                    }
                                ],
                            }
                            yield f"data: {json.dumps(openai_chunk)}\n\n"
                    except (json.JSONDecodeError, KeyError):
                        continue
                elif line.strip() == "event: message_stop":
                    openai_done = {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop",
                            }
                        ],
                    }
                    yield f"data: {json.dumps(openai_done)}\n\n"
                    yield "data: [DONE]\n\n"

    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        return request.estimate_tokens()
