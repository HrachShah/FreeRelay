"""
FreeRelay — Demo/Mock Provider
=================================
Simulates LLM responses for testing/demo without API keys.
"""

from __future__ import annotations

import asyncio
import json
import random
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


class DemoProvider:
    """Mock provider that returns simulated responses."""

    name = "demo"
    base_url = ""
    supported_features = {"streaming"}

    _default_model = "demo-model"

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        raw = request.messages[-1].content if request.messages else ""
        content = _extract_text(raw)
        response_text = self._generate_response(content)

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
            created=int(time.time()),
            model=self._default_model,
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=response_text),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=len(content.split()),
                completion_tokens=len(response_text.split()),
                total_tokens=(len(content.split()) + len(response_text.split())),
            ),
        )

    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        raw = request.messages[-1].content if request.messages else ""
        content = _extract_text(raw)
        response_text = self._generate_response(content)

        words = response_text.split()
        for word in words:
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": self._default_model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": word + " "},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n"
            await asyncio.sleep(0.02)

        done = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": self._default_model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(done)}\n\n"
        yield "data: [DONE]\n\n"

    def _generate_response(self, content: str) -> str:
        content_lower = content.lower()

        if "hello" in content_lower or "hi" in content_lower:
            return "Hello! I'm FreeRelay, your AI gateway. How can I help you today?"
        if "name" in content_lower:
            return (
                "I'm FreeRelay, an open-source AI gateway that routes "
                "requests across multiple free LLM providers."
            )
        if "code" in content_lower or "function" in content_lower:
            return (
                "Here's a simple Python function:\n\n"
                "```python\n"
                "def greet(name):\n"
                "    return f'Hello, {name}!'\n\n"
                "print(greet('World'))\n"
                "```"
            )
        if "list" in content_lower or "items" in content_lower:
            return "1. First item\n2. Second item\n3. Third item"
        if "?" in content_lower:
            return "That's a great question! Let me think about it..."
        responses = [
            "I understand your message. This is a demo response from FreeRelay's built-in provider.",
            "Thanks for your input! In a real setup, I'd route this to Groq, Google, or OpenRouter.",
            "FreeRelay aggregates multiple free LLM tiers into one reliable endpoint.",
            "This demo shows FreeRelay working without any API keys configured.",
        ]
        return random.choice(responses)

    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        return request.estimate_tokens()
