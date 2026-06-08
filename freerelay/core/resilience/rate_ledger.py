"""
FreeRelay — RateLedger: per-provider-key rolling window rate tracking.

Tracks RPM / RPD / TPM / TPD (requests-per-minute, requests-per-day,
tokens-per-minute, tokens-per-day) for each provider+key combination.
The engine consults this before routing a request and records usage after.

This complements the existing BudgetForecaster (which does EWMA token
cost estimation) — the ledger is the hard cap enforcement layer.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field


@dataclass
class _Window:
    """Sliding window counter for a single metric."""

    max_value: int | None  # None = unlimited
    window_secs: float
    _timestamps: collections.deque[tuple[float, int]] = field(
        default_factory=collections.deque
    )

    def record(self, amount: int = 1) -> None:
        self._timestamps.append((time.monotonic(), amount))

    def total(self) -> int:
        cutoff = time.monotonic() - self.window_secs
        while self._timestamps and self._timestamps[0][0] < cutoff:
            self._timestamps.popleft()
        return sum(v for _, v in self._timestamps)

    def can_use(self, amount: int = 1) -> bool:
        if self.max_value is None:
            return True
        return self.total() + amount <= self.max_value


@dataclass
class _ProviderLimits:
    """Per-provider rate windows."""

    rpm: _Window
    rpd: _Window
    tpm: _Window
    tpd: _Window

    def can_use(self, est_tokens: int) -> bool:
        return (
            self.rpm.can_use(1)
            and self.rpd.can_use(1)
            and self.tpm.can_use(est_tokens)
            and self.tpd.can_use(est_tokens)
        )

    def record(self, tokens: int) -> None:
        self.rpm.record(1)
        self.rpd.record(1)
        self.tpm.record(tokens)
        self.tpd.record(tokens)

    def stats(self) -> dict[str, object]:
        return {
            "rpm_used": self.rpm.total(),
            "rpm_limit": self.rpm.max_value,
            "rpd_used": self.rpd.total(),
            "rpd_limit": self.rpd.max_value,
            "tpm_used": self.tpm.total(),
            "tpm_limit": self.tpm.max_value,
            "tpd_used": self.tpd.total(),
            "tpd_limit": self.tpd.max_value,
        }


class RateLedger:
    """
    Tracks rate-limit consumption per provider.

    Usage::

        ledger = RateLedger()
        ledger.set_limits("groq", rpm=30, rpd=None, tpm=6000, tpd=500_000)

        # Before routing:
        if not ledger.can_use("groq", est_tokens=200):
            # skip this provider

        # After a successful response:
        ledger.record("groq", tokens=186)
    """

    def __init__(self) -> None:
        self._providers: dict[str, _ProviderLimits] = {}

    def set_limits(
        self,
        provider: str,
        *,
        rpm: int | None = None,
        rpd: int | None = None,
        tpm: int | None = None,
        tpd: int | None = None,
    ) -> None:
        """Register (or update) limits for a provider."""
        self._providers[provider] = _ProviderLimits(
            rpm=_Window(max_value=rpm, window_secs=60.0),
            rpd=_Window(max_value=rpd, window_secs=86400.0),
            tpm=_Window(max_value=tpm, window_secs=60.0),
            tpd=_Window(max_value=tpd, window_secs=86400.0),
        )

    def can_use(self, provider: str, est_tokens: int = 100) -> bool:
        """
        Return True if the provider is within all rate limits.

        Providers with no registered limits always return True.
        """
        limits = self._providers.get(provider)
        if limits is None:
            return True
        return limits.can_use(est_tokens)

    def record(self, provider: str, tokens: int) -> None:
        """Record a completed request for *provider* consuming *tokens*."""
        limits = self._providers.get(provider)
        if limits is not None:
            limits.record(tokens)

    def stats(self, provider: str) -> dict[str, object]:
        """Return current usage stats for *provider*."""
        limits = self._providers.get(provider)
        if limits is None:
            return {}
        return limits.stats()
