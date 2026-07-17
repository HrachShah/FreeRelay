from freerelay.data_plane.ingress.rate_limit import RateLimiter


async def test_rate_limiter_rejects_non_positive_limits():
    limiter = RateLimiter()

    for limit in (0, -1):
        try:
            await limiter.check_rate_limit("tenant", limit)
        except ValueError as exc:
            assert str(exc) == "rate limit must be a positive integer"
        else:
            raise AssertionError("non-positive limits must be rejected")
