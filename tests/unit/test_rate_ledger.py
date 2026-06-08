"""Tests for RateLedger per-provider sliding-window rate tracking."""

from __future__ import annotations

from freerelay.core.resilience.rate_ledger import RateLedger


def test_no_limits_always_allows() -> None:
    ledger = RateLedger()
    # Provider with no registered limits
    assert ledger.can_use("unknown_provider", est_tokens=9999)


def test_rpm_enforced() -> None:
    ledger = RateLedger()
    ledger.set_limits("groq", rpm=2)
    assert ledger.can_use("groq")
    ledger.record("groq", tokens=100)
    assert ledger.can_use("groq")
    ledger.record("groq", tokens=100)
    # 2 requests recorded, limit=2 — next one should be blocked
    assert not ledger.can_use("groq")


def test_tpm_enforced() -> None:
    ledger = RateLedger()
    ledger.set_limits("mistral", tpm=500)
    ledger.record("mistral", tokens=300)
    assert ledger.can_use("mistral", est_tokens=100)
    assert not ledger.can_use("mistral", est_tokens=300)


def test_tpd_enforced() -> None:
    ledger = RateLedger()
    ledger.set_limits("together", tpd=1000)
    ledger.record("together", tokens=800)
    assert not ledger.can_use("together", est_tokens=300)
    assert ledger.can_use("together", est_tokens=100)


def test_stats_returns_usage() -> None:
    ledger = RateLedger()
    ledger.set_limits("groq", rpm=30, tpm=6000)
    ledger.record("groq", tokens=500)
    stats = ledger.stats("groq")
    assert stats["rpm_used"] == 1
    assert stats["tpm_used"] == 500
    assert stats["rpm_limit"] == 30
    assert stats["tpm_limit"] == 6000


def test_stats_empty_for_unknown() -> None:
    ledger = RateLedger()
    assert ledger.stats("nope") == {}


def test_unlimited_limits_allow_any() -> None:
    ledger = RateLedger()
    ledger.set_limits("google", rpm=None, tpm=None)
    for _ in range(100):
        ledger.record("google", tokens=10000)
    assert ledger.can_use("google", est_tokens=99999)
