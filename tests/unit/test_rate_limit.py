from unittest.mock import patch

import pytest

from freerelay.middleware.rate_limit import TokenBucket


@pytest.mark.parametrize("rate, capacity", [(0, 1), (-1, 1), (1, 0), (1, -1)])
def test_token_bucket_rejects_non_positive_settings(rate, capacity):
    with pytest.raises(ValueError):
        TokenBucket(rate, capacity)


def test_token_bucket_uses_monotonic_clock_for_refills():
    with patch("freerelay.middleware.rate_limit.time.monotonic", side_effect=[10.0, 10.0, 10.0, 11.0]):
        bucket = TokenBucket(rate=1, capacity=1)
        assert bucket.consume()
        assert not bucket.consume()

        bucket.tokens = 0
        assert bucket.consume()
