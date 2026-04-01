"""
FreeRelay — EWMA Budget Forecaster (§10)
============================================
Predictive token consumption forecasting using
Exponential Weighted Moving Average.
Separate from budget.py — provides the forecasting math.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("freerelay.forecast")


@dataclass
class ForecastSnapshot:
    """Point-in-time forecast data."""

    provider: str
    current_rate: float = 0.0  # tokens per minute (current)
    ewma_rate: float = 0.0  # smoothed rate
    projected_remaining: int = 0  # tokens remaining before exhaustion
    minutes_until_exhaustion: float = float("inf")
    budget_ratio: float = 1.0  # 0.0 = exhausted, 1.0 = full


class EWMAForecaster:
    """
    Exponential Weighted Moving Average consumption forecaster.

    Predicts when a provider will exhaust its daily token limit
    based on observed consumption patterns.

    EWMA Formula (§10.1):
        alpha = 0.3 (smoothing factor)
        ewma_rate = alpha * current_rate + (1 - alpha) * previous_ewma_rate
    """

    def __init__(
        self,
        alpha: float = 0.3,
        safety_margin_tokens: int = 10_000,
    ) -> None:
        self.alpha = alpha
        self.safety_margin = safety_margin_tokens

        # Per-provider state
        self._rates: dict[str, float] = {}  # ewma_rate per provider
        self._minute_tokens: dict[str, int] = {}  # tokens in current minute
        self._minute_start: dict[str, float] = {}  # when current minute started

    def record_tokens(self, provider: str, tokens: int) -> None:
        """
        Record token consumption.

        Updates the per-minute counter and triggers EWMA update
        when crossing a minute boundary.
        """
        now = time.time()
        minute_start = self._minute_start.get(provider, now)

        if now - minute_start >= 60:
            # Minute boundary crossed — update EWMA
            current_rate = self._minute_tokens.get(provider, 0)
            prev_ewma = self._rates.get(provider, 0.0)
            self._rates[provider] = (
                self.alpha * current_rate + (1 - self.alpha) * prev_ewma
            )
            self._minute_tokens[provider] = 0
            self._minute_start[provider] = now
        else:
            self._minute_tokens[provider] = (
                self._minute_tokens.get(provider, 0) + tokens
            )

    def get_forecast(
        self,
        provider: str,
        tokens_used_today: int,
        daily_limit: int | None,
    ) -> ForecastSnapshot:
        """
        Get a forecast snapshot for a provider.

        Args:
            provider: Provider name.
            tokens_used_today: Total tokens consumed today.
            daily_limit: Daily token limit (None = unlimited).

        Returns:
            ForecastSnapshot with projections.
        """
        ewma_rate = self._rates.get(provider, 0.0)

        if daily_limit is None:
            return ForecastSnapshot(
                provider=provider,
                ewma_rate=ewma_rate,
                budget_ratio=1.0,
            )

        remaining = daily_limit - tokens_used_today
        budget_ratio = (
            max(0.0, min(1.0, remaining / daily_limit)) if daily_limit > 0 else 0.0
        )

        if ewma_rate <= 0 or remaining <= 0:
            return ForecastSnapshot(
                provider=provider,
                ewma_rate=ewma_rate,
                projected_remaining=max(0, remaining - self.safety_margin),
                minutes_until_exhaustion=float("inf") if remaining > 0 else 0,
                budget_ratio=budget_ratio,
            )

        minutes_until_exhaustion = remaining / ewma_rate
        projected_remaining = max(0, remaining - self.safety_margin)

        return ForecastSnapshot(
            provider=provider,
            ewma_rate=round(ewma_rate, 1),
            projected_remaining=projected_remaining,
            minutes_until_exhaustion=round(minutes_until_exhaustion, 1),
            budget_ratio=budget_ratio,
        )

    def should_route_away(
        self,
        provider: str,
        tokens_used_today: int,
        daily_limit: int | None,
    ) -> bool:
        """
        Check if we should route away from this provider
        based on projected budget exhaustion.

        Routes away when projected remaining < safety margin.
        """
        if daily_limit is None:
            return False

        remaining = daily_limit - tokens_used_today
        if remaining <= 0:
            return True

        if remaining < self.safety_margin:
            return True

        ewma_rate = self._rates.get(provider, 0.0)
        if ewma_rate > 0:
            minutes_left = remaining / ewma_rate
            if minutes_left < 15:
                return True

        return False
