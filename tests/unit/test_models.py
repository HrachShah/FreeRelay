"""
Tests — OpenAI Models
========================
Verify Pydantic models parse and serialize correctly.
"""

import pytest

from freerelay.core.models.openai import (
    ChatCompletionChunk,
    ChatCompletionRequest,
    ChatCompletionResponse,
    Message,
    Usage,
)


class TestChatCompletionRequest:
    def test_basic_parse(self) -> None:
        req = ChatCompletionRequest(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert req.model == "gpt-4"
        assert len(req.messages) == 1
        assert req.messages[0].role == "user"

    def test_defaults(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hi"}],
        )
        assert req.stream is False
        assert req.n == 1
        assert req.temperature is None

    def test_streaming_flag(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hi"}],
            stream=True,
        )
        assert req.is_streaming()

    def test_token_estimation(self) -> None:
        req = ChatCompletionRequest(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "x" * 400},
            ],
        )
        est = req.estimate_tokens()
        assert 90 < est < 120  # ~415 chars / 4

    def test_with_tools(self) -> None:
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hi"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"},
                },
            }],
        )
        assert len(req.tools) == 1
        assert req.tools[0].function.name == "get_weather"

    def test_multi_modal_content(self) -> None:
        req = ChatCompletionRequest(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
                ],
            }],
        )
        assert isinstance(req.messages[0].content, list)
        assert len(req.messages[0].content) == 2


class TestChatCompletionResponse:
    def test_from_text(self) -> None:
        resp = ChatCompletionResponse.from_text("Hello!", model="test")
        assert resp.model == "test"
        assert resp.choices[0].message.content == "Hello!"
        assert resp.choices[0].finish_reason == "stop"
        assert resp.id.startswith("chatcmpl-")

    def test_error_body(self) -> None:
        err = ChatCompletionResponse.error_body("bad request", 400)
        assert err["error"]["message"] == "bad request"
        assert err["error"]["code"] == 400

    def test_serialization(self) -> None:
        resp = ChatCompletionResponse.from_text("hi")
        data = resp.model_dump(exclude_none=True)
        assert data["object"] == "chat.completion"
        assert isinstance(data["created"], int)


class TestStreamChunk:
    def test_to_sse(self) -> None:
        chunk = ChatCompletionChunk(
            model="test",
            choices=[{
                "index": 0,
                "delta": {"content": "Hello"},
                "finish_reason": None,
            }],
        )
        sse = chunk.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        assert '"Hello"' in sse

    def test_done_event(self) -> None:
        assert ChatCompletionChunk.done_event() == "data: [DONE]\n\n"
