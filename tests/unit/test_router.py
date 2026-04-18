"""
Tests — Router Integration
=============================
Verify end-to-end routing with mocked providers.
"""

from collections.abc import AsyncIterator

import pytest

from freerelay.config.settings import Settings
from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Message,
    Usage,
)
from freerelay.core.routing.engine import RoutingEngine
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError


class MockProvider(BaseProvider):
    """A mock provider for testing."""

    name = "mock"
    base_url = "http://mock"
    supported_features = {"streaming"}

    def __init__(self, should_fail: bool = False, fail_with_429: bool = False) -> None:
        self.should_fail = should_fail
        self.fail_with_429 = fail_with_429
        self.call_count = 0

    async def complete(
        self, request: ChatCompletionRequest, api_key: str
    ) -> ChatCompletionResponse:
        self.call_count += 1
        if self.fail_with_429:
            raise RateLimitError(provider_name=self.name)
        if self.should_fail:
            raise ProviderError("mock error", 500, self.name)
        return ChatCompletionResponse.from_text(
            f"Hello from {self.name}!",
            model="mock-model",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def stream(
        self, request: ChatCompletionRequest, api_key: str
    ) -> AsyncIterator[str]:
        self.call_count += 1
        if self.fail_with_429:
            raise RateLimitError(provider_name=self.name)
        if self.should_fail:
            raise ProviderError("mock error", 500, self.name)
        yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        yield "data: [DONE]\n\n"

    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        return 10


@pytest.fixture
def settings() -> Settings:
    return Settings(enable_chaos=False)


@pytest.fixture
def request_obj() -> ChatCompletionRequest:
    return ChatCompletionRequest(
        messages=[Message(role="user", content="Hello")],
    )


class TestRoutingEngine:
    @pytest.mark.asyncio
    async def test_routes_to_available_provider(
        self, settings: Settings, request_obj: ChatCompletionRequest
    ) -> None:
        engine = RoutingEngine(settings)
        mock = MockProvider()
        engine.register_provider(mock, "key123")

        resp = await engine.route(request_obj)
        assert "Hello from mock!" in (resp.choices[0].message.content or "")
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_fallback_on_rate_limit(
        self, settings: Settings, request_obj: ChatCompletionRequest
    ) -> None:
        engine = RoutingEngine(settings)

        failing = MockProvider(fail_with_429=True)
        failing.name = "failing"

        working = MockProvider()
        working.name = "working"

        engine.register_provider(failing, "key1")
        engine.register_provider(working, "key2")

        resp = await engine.route(request_obj)
        assert "Hello from working!" in (resp.choices[0].message.content or "")
        assert failing.call_count == 1
        assert working.call_count == 1

    @pytest.mark.asyncio
    async def test_all_providers_fail(
        self, settings: Settings, request_obj: ChatCompletionRequest
    ) -> None:
        engine = RoutingEngine(settings)
        engine.register_provider(MockProvider(should_fail=True), "key1")

        resp = await engine.route(request_obj)
        content = resp.choices[0].message.content
        assert isinstance(content, str) and "failed" in content.lower()

    @pytest.mark.asyncio
    async def test_no_providers(
        self, settings: Settings, request_obj: ChatCompletionRequest
    ) -> None:
        engine = RoutingEngine(settings)
        resp = await engine.route(request_obj)
        content = resp.choices[0].message.content
        assert isinstance(content, str) and "no providers" in content.lower()

    @pytest.mark.asyncio
    async def test_stream_routing(
        self, settings: Settings, request_obj: ChatCompletionRequest
    ) -> None:
        engine = RoutingEngine(settings)
        engine.register_provider(MockProvider(), "key1")

        chunks: list[str] = []
        async for chunk in engine.route_stream(request_obj):
            chunks.append(chunk)

        assert len(chunks) >= 1
        assert any("DONE" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_stats_output(self, settings: Settings) -> None:
        engine = RoutingEngine(settings)
        engine.register_provider(MockProvider(), "key1")

        stats = engine.get_stats()
        assert len(stats) == 1
        assert stats[0]["name"] == "mock"
        assert "circuit" in stats[0]
        assert "budget" in stats[0]
