"""
FreeRelay — Redis Budget Forecaster
====================================
Distributed token budget tracking across multiple Data Plane instances using Redis.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from redis.asyncio import Redis

from freerelay.core.resilience.budget import BudgetForecaster

logger = logging.getLogger("freerelay.resilience.redis_budget")

class RedisBudgetForecaster(BudgetForecaster):
    """
    Redis-backed budget forecaster for distributed token tracking.
    
    Keys:
      freerelay:budget:{provider}:used_today     (string: integer)
      freerelay:budget:{provider}:used_minute    (string: integer)
      freerelay:budget:{provider}:ewma_rate      (string: float)
      freerelay:budget:{provider}:last_updated   (string: timestamp)
      freerelay:budget:{provider}:limit          (string: integer)
    """
    
    def __init__(
        self,
        redis: Redis,
        alpha: float = 0.3,
        safety_margin: int = 10_000,
        key_prefix: str = "freerelay:budget:",
    ) -> None:
        # We don't call super().__init__ because we override everything
        self.redis = redis
        self.alpha = alpha
        self.safety_margin = safety_margin
        self.prefix = key_prefix

    def _get_keys(self, provider: str) -> dict[str, str]:
        p = f"{self.prefix}{provider}:"
        return {
            "used_today": f"{p}used_today",
            "used_minute": f"{p}used_minute",
            "ewma_rate": f"{p}ewma_rate",
            "last_updated": f"{p}last_updated",
            "limit": f"{p}limit",
        }

    async def set_daily_limit(self, provider: str, limit: int | None) -> None:
        keys = self._get_keys(provider)
        if limit is None:
            await self.redis.delete(keys["limit"])
        else:
            await self.redis.set(keys["limit"], str(limit))

    async def record_tokens(self, provider: str, tokens: int) -> None:
        keys = self._get_keys(provider)
        now = time.time()
        
        # Get current state
        last_updated_str = await self.redis.get(keys["last_updated"])
        last_updated = float(last_updated_str) if last_updated_str else now
        
        ewma_rate_str = await self.redis.get(keys["ewma_rate"])
        ewma_rate = float(ewma_rate_str) if ewma_rate_str else 0.0
        
        # Check minute boundary
        elapsed = now - last_updated
        if elapsed >= 60:
            used_minute_str = await self.redis.get(keys["used_minute"])
            used_minute = int(used_minute_str) if used_minute_str else 0
            
            full_minutes = int(elapsed / 60)
            # Decay EWMA for idle minutes
            for _ in range(min(full_minutes, 10)):
                ewma_rate = self.alpha * 0.0 + (1 - self.alpha) * ewma_rate
            
            # Update EWMA with last minute usage
            ewma_rate = self.alpha * used_minute + (1 - self.alpha) * ewma_rate
            
            # Update Redis
            await self.redis.set(keys["ewma_rate"], str(ewma_rate))
            await self.redis.set(keys["used_minute"], "0")
            await self.redis.set(keys["last_updated"], str(now))
        
        # Increment counters
        await self.redis.incrby(keys["used_today"], tokens)
        await self.redis.incrby(keys["used_minute"], tokens)

    async def get_budget_score(self, provider: str) -> float:
        keys = self._get_keys(provider)
        
        limit_str = await self.redis.get(keys["limit"])
        if limit_str is None:
            return 1.0
            
        limit = int(limit_str)
        used_today_str = await self.redis.get(keys["used_today"])
        used_today = int(used_today_str) if used_today_str else 0
        
        remaining = limit - used_today
        if remaining <= 0:
            return 0.0
            
        return max(0.0, min(1.0, remaining / limit))

    async def is_budget_exhausted(self, provider: str) -> bool:
        keys = self._get_keys(provider)
        
        limit_str = await self.redis.get(keys["limit"])
        if limit_str is None:
            return False
            
        limit = int(limit_str)
        used_today_str = await self.redis.get(keys["used_today"])
        used_today = int(used_today_str) if used_today_str else 0
        
        remaining = limit - used_today
        if remaining <= 0:
            return True
            
        ewma_rate_str = await self.redis.get(keys["ewma_rate"])
        ewma_rate = float(ewma_rate_str) if ewma_rate_str else 0.0
        
        if ewma_rate > 0:
            minutes_left = remaining / ewma_rate
            if minutes_left < 15 and remaining < self.safety_margin:
                return True
                
        return remaining < self.safety_margin

    async def reset_daily(self, provider: str) -> None:
        keys = self._get_keys(provider)
        await self.redis.set(keys["used_today"], "0")
        await self.redis.set(keys["used_minute"], "0")

    async def get_stats(self, provider: str) -> dict[str, object]:
        keys = self._get_keys(provider)
        
        used_today_str = await self.redis.get(keys["used_today"])
        used_today = int(used_today_str) if used_today_str else 0
        
        ewma_rate_str = await self.redis.get(keys["ewma_rate"])
        ewma_rate = float(ewma_rate_str) if ewma_rate_str else 0.0
        
        limit_str = await self.redis.get(keys["limit"])
        limit = int(limit_str) if limit_str else None
        
        score = await self.get_budget_score(provider)
        exhausted = await self.is_budget_exhausted(provider)
        
        return {
            "provider": provider,
            "tokens_used_today": used_today,
            "ewma_rate_per_min": round(ewma_rate, 1),
            "daily_limit": limit,
            "budget_score": round(score, 3),
            "exhausted": exhausted,
        }
