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
