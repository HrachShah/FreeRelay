"""Tests for rate limiting configuration and token consumption."""

import pytest

from freerelay.middleware.rate_limit import RateLimitMiddleware


@pytest.mark.parametrize(
    ("requests_per_minute", "burst_capacity", "message"),
    [
        (0, 10, "requests_per_minute must be at least 1"),
        (60, 0, "burst_capacity must be at least 1"),
    ],
)
def test_rejects_non_positive_limits(
    requests_per_minute: int, burst_capacity: int, message: str
) -> None:
    """Invalid limits should fail during startup instead of denying all traffic."""
    with pytest.raises(ValueError, match=message):
        RateLimitMiddleware(
            app=lambda scope, receive, send: None,
            requests_per_minute=requests_per_minute,
            burst_capacity=burst_capacity,
        )


def test_fallback_removes_expired_entries_for_idle_namespaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expired timestamps should be discarded even when the next request is allowed."""
    from freerelay.data_plane.ingress.rate_limit import _InMemoryWindow

    now = 100.0
    monkeypatch.setattr("freerelay.data_plane.ingress.rate_limit.time.time", lambda: now)
    window = _InMemoryWindow()
    window.check("tenant", limit=2, window=10)
    now = 111.0

    result = window.check("tenant", limit=2, window=10)

    assert result.allowed
    assert window._windows["tenant"] == [111.0]
