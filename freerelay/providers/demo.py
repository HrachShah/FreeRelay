"""
FreeRelay — Demo/Mock Provider
=================================
Simulates LLM responses for testing/demo without API keys.
"""

from __future__ import annotations

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
        content = request.messages[-1].content if request.messages else ""
        response_text = self._generate_response(content, request)

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
                total_tokens=len(content.split()) + len(response_text.split()),
            ),
        )

    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        content = request.messages[-1].content if request.messages else ""
        response_text = self._generate_response(content, request)

        words = response_text.split()
        for i, word in enumerate(words):
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
            import json

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
        import json

        yield f"data: {json.dumps(done)}\n\n"
        yield "data: [DONE]\n\n"

    def _generate_response(self, content: str, request: ChatCompletionRequest) -> str:
        content_lower = content.lower()

        if "hello" in content_lower or "hi" in content_lower:
            return "Hello! I'm FreeRelay, your AI gateway. How can I help you today?"
        elif "name" in content_lower:
            return "I'm FreeRelay, an open-source AI gateway that routes requests across multiple free LLM providers."
        elif "code" in content_lower or "function" in content_lower:
            return "Here's a simple Python function:\n\n```python\ndef greet(name):\n    return f'Hello, {name}!'\n\nprint(greet('World'))\n```"
        elif "list" in content_lower or "items" in content_lower:
            return "1. First item\n2. Second item\n3. Third item"
        elif "?" in content_lower:
            return "That's a great question! Let me think about it..."
        else:
            responses = [
                "I understand your message. This is a demo response from FreeRelay's built-in provider.",
                "Thanks for your input! In a real setup, I'd route this to Groq, Google, or OpenRouter.",
                "FreeRelay aggregates multiple free LLM tiers into one reliable endpoint.",
                "This demo shows FreeRelay working without any API keys configured.",
            ]
            import random

            return random.choice(responses)

    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        return request.estimate_tokens()


import asyncio
