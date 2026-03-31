"""
FreeRelay — Budget Forecaster (§10)
=====================================
EWMA-based token consumption forecasting.
Predicts when a provider will exhaust its daily limit
and routes away 15 min before hitting the wall.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BudgetState:
    """Token budget state for a single provider/key."""
    tokens_used_today: int = 0
    tokens_used_this_minute: int = 0
    ewma_rate: float = 0.0  # tokens per minute
    last_updated_ts: float = field(default_factory=time.time)
    daily_reset_ts: float = 0.0  # next midnight UTC
    daily_limit: int | None = None  # None = unlimited


class BudgetForecaster:
    """
    In-memory budget tracker with EWMA forecasting.

    EWMA Formula (§10.1):
        alpha = 0.3
        ewma_rate = alpha * current_rate + (1 - alpha) * previous_ewma_rate

    Routes away when:
        projected_remaining < SAFETY_MARGIN_TOKENS
    """

    def __init__(
        self,
        alpha: float = 0.3,
        safety_margin: int = 10_000,
    ) -> None:
        self.alpha = alpha
        self.safety_margin = safety_margin
        self._budgets: dict[str, BudgetState] = {}

    def _get_state(self, provider: str) -> BudgetState:
        if provider not in self._budgets:
            self._budgets[provider] = BudgetState()
        return self._budgets[provider]

    def set_daily_limit(self, provider: str, limit: int | None) -> None:
        """Configure daily token limit for a provider."""
        state = self._get_state(provider)
        state.daily_limit = limit

    def record_tokens(self, provider: str, tokens: int) -> None:
        """Record token usage after a request completes."""
        state = self._get_state(provider)
        now = time.time()

        # Check if we've crossed a minute boundary
        elapsed = now - state.last_updated_ts
        if elapsed >= 60:
            # Update EWMA with the minute's consumption
            current_rate = state.tokens_used_this_minute
            state.ewma_rate = (
                self.alpha * current_rate
                + (1 - self.alpha) * state.ewma_rate
            )
            state.tokens_used_this_minute = 0
            state.last_updated_ts = now

        state.tokens_used_today += tokens
        state.tokens_used_this_minute += tokens

    def get_budget_score(self, provider: str) -> float:
        """
        Score for routing engine (0.0-1.0).
        1.0 = plenty of budget, 0.0 = exhausted.
        """
        state = self._get_state(provider)

        if state.daily_limit is None:
            return 1.0  # No limit = full budget

        remaining = state.daily_limit - state.tokens_used_today
        if remaining <= 0:
            return 0.0

        ratio = remaining / state.daily_limit
        return max(0.0, min(1.0, ratio))

    def is_budget_exhausted(self, provider: str) -> bool:
        """Check if provider is predicted to exhaust its budget."""
        state = self._get_state(provider)

        if state.daily_limit is None:
            return False

        remaining = state.daily_limit - state.tokens_used_today
        if remaining <= 0:
            return True

        # Project consumption for the remaining time
        if state.ewma_rate > 0:
            minutes_left = max(1, remaining / state.ewma_rate)
            # If we'd run out within 15 minutes, flag it
            if minutes_left < 15 and remaining < self.safety_margin:
                return True

        return remaining < self.safety_margin

    def get_stats(self, provider: str) -> dict[str, object]:
        """Budget stats for dashboard."""
        state = self._get_state(provider)
        return {
            "provider": provider,
            "tokens_used_today": state.tokens_used_today,
            "ewma_rate_per_min": round(state.ewma_rate, 1),
            "daily_limit": state.daily_limit,
            "budget_score": round(self.get_budget_score(provider), 3),
            "exhausted": self.is_budget_exhausted(provider),
        }

    def reset_daily(self, provider: str) -> None:
        """Reset daily counters (call at midnight UTC)."""
        state = self._get_state(provider)
        state.tokens_used_today = 0
        state.tokens_used_this_minute = 0
