"""Tests for KeyPool multi-key rotation and cooldown."""

from __future__ import annotations

import time

import pytest

from freerelay.providers.key_pool import KeyPool


def test_single_key_returns_it() -> None:
    pool = KeyPool(["sk-abc"])
    assert pool.next() == "sk-abc"
    assert pool.next() == "sk-abc"


def test_round_robin() -> None:
    pool = KeyPool(["a", "b", "c"])
    keys = [pool.next() for _ in range(6)]
    assert keys == ["a", "b", "c", "a", "b", "c"]


def test_cooldown_skips_key() -> None:
    pool = KeyPool(["a", "b"])
    pool.cooldown("a", secs=60)
    # next() should skip 'a' and return 'b'
    assert pool.next() == "b"
    assert pool.next() == "b"


def test_all_cooled_returns_soonest() -> None:
    pool = KeyPool(["a", "b"], cooldown_secs=10)
    pool.cooldown("a", secs=100)
    pool.cooldown("b", secs=10)
    # both are cooled; 'b' expires sooner
    result = pool.next()
    assert result == "b"


def test_from_csv_single() -> None:
    pool = KeyPool.from_csv("sk-abc")
    assert len(pool) == 1
    assert pool.next() == "sk-abc"


def test_from_csv_multiple() -> None:
    pool = KeyPool.from_csv("sk-1, sk-2, sk-3")
    assert len(pool) == 3
    assert pool.next() == "sk-1"
    assert pool.next() == "sk-2"


def test_from_csv_empty_raises() -> None:
    with pytest.raises(ValueError):
        KeyPool.from_csv("")


def test_primary_is_first_key() -> None:
    pool = KeyPool(["first", "second"])
    assert pool.primary == "first"


def test_all_cooled_flag() -> None:
    pool = KeyPool(["a"])
    assert not pool.all_cooled()
    pool.cooldown("a", secs=60)
    assert pool.all_cooled()


def test_cooldown_expires() -> None:
    pool = KeyPool(["a", "b"], cooldown_secs=0.05)
    pool.cooldown("a")
    assert pool.next() == "b"
    time.sleep(0.1)
    # After expiry, 'a' should be available again
    assert pool.next() == "a"
