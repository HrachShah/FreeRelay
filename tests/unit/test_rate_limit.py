from unittest.mock import AsyncMock, Mock

import pytest

from freerelay.middleware.rate_limit import RateLimitMiddleware
from freerelay.data_plane.ingress.rate_limit import _InMemoryWindow


@pytest.mark.asyncio
async def test_only_exact_exempt_paths_and_children_bypass_rate_limit():
    middleware = RateLimitMiddleware(Mock(), requests_per_minute=60, burst_capacity=1)
    call_next = AsyncMock(return_value=Mock())

    for path in ("/v1/health", "/v1/health/check", "/v1/metrics", "/v1/metrics/prometheus"):
        request = Mock()
        request.url.path = path
        request.state = type("State", (), {})()
        request.client = None
        await middleware.dispatch(request, call_next)

    assert call_next.await_count == 4
    assert middleware._buckets == {}


@pytest.mark.asyncio
async def test_similarly_named_endpoint_is_still_rate_limited():
    middleware = RateLimitMiddleware(Mock(), requests_per_minute=60, burst_capacity=1)
    call_next = AsyncMock(return_value=Mock())
    request = Mock()
    request.url.path = "/v1/healthcheck"
    request.state.user_id = "user-1"
    request.client.host = "127.0.0.1"

    await middleware.dispatch(request, call_next)
    await middleware.dispatch(request, call_next)

    assert call_next.await_count == 1
    assert middleware._buckets["user-1"].tokens < 1


def test_fallback_reset_timestamp_rounds_up_fractional_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset metadata must not tell callers to retry before the window expires."""
    now = 100.25
    monkeypatch.setattr("freerelay.data_plane.ingress.rate_limit.time.time", lambda: now)
    window = _InMemoryWindow()

    first = window.check("tenant", limit=1, window=10)
    second = window.check("tenant", limit=1, window=10)

    assert first.reset_ts == 111
    assert not second.allowed
    assert second.reset_ts == 111
