"""
FreeRelay — Redis Circuit Breaker
==================================
Shared circuit state across multiple Data Plane instances using Redis.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from redis.asyncio import Redis

from freerelay.core.resilience.circuit_breaker import CircuitBreaker, CircuitState

logger = logging.getLogger("freerelay.resilience.redis_breaker")

class RedisCircuitBreaker(CircuitBreaker):
    """
    Redis-backed circuit breaker for distributed state.
    
    Keys:
      freerelay:circuit:{provider}:state       (string: CLOSED, OPEN, HALF_OPEN)
      freerelay:circuit:{provider}:failures    (sorted set: timestamps)
      freerelay:circuit:{provider}:open_since  (string: timestamp)
    """
    
    def __init__(
        self,
        redis: Redis,
        provider_name: str,
        failure_threshold: int = 5,
        failure_window: int = 60,
        recovery_timeout: int = 30,
        key_prefix: str = "freerelay:circuit:",
    ) -> None:
        # We don't call super().__init__ because we override almost everything
        self.redis = redis
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.failure_window = failure_window
        self.recovery_timeout = recovery_timeout
        self.prefix = f"{key_prefix}{provider_name}:"
        
        self._state_key = f"{self.prefix}state"
        self._failures_key = f"{self.prefix}failures"
        self._open_since_key = f"{self.prefix}open_since"

    async def _get_remote_state(self) -> CircuitState:
        state_str = await self.redis.get(self._state_key)
        if state_str is None:
            return CircuitState.CLOSED
        return CircuitState(state_str)

    async def _check_auto_transition(self) -> CircuitState:
        state = await self._get_remote_state()
        if state == CircuitState.OPEN:
            open_since = await self.redis.get(self._open_since_key)
            if open_since and (time.time() - float(open_since) >= self.recovery_timeout):
                # Transition to HALF_OPEN
                await self.redis.set(self._state_key, CircuitState.HALF_OPEN)
                return CircuitState.HALF_OPEN
        return state

    @property
    def state(self) -> CircuitState:
        # This property is tricky because it's async in reality.
        # For simplicity in the rest of the code, we might need to rethink this
        # or just accept that 'state' property might be slightly stale if used without can_execute.
        # But for now, we'll keep it as is, maybe return CLOSED by default if not synced.
        return CircuitState.CLOSED 

    async def can_execute(self) -> bool:
        state = await self._check_auto_transition()
        if state == CircuitState.CLOSED:
            return True
        return state == CircuitState.HALF_OPEN

    async def record_success(self) -> None:
        state = await self._get_remote_state()
        if state == CircuitState.HALF_OPEN:
            await self.redis.set(self._state_key, CircuitState.CLOSED)
            await self.redis.delete(self._failures_key)
            await self.redis.delete(self._open_since_key)

    async def record_failure(self, status_code: int | None = None) -> None:
        from freerelay.core.resilience.circuit_breaker import _FAILURE_STATUS_CODES
        
        if status_code is not None and status_code not in _FAILURE_STATUS_CODES:
            return

        now = time.time()
        state = await self._check_auto_transition()
        
        if state == CircuitState.HALF_OPEN:
            await self.redis.set(self._state_key, CircuitState.OPEN)
            await self.redis.set(self._open_since_key, str(now))
            return

        # Track failure
        await self.redis.zadd(self._failures_key, {str(now): now})
        # Prune old failures
        await self.redis.zremrangebyscore(self._failures_key, 0, now - self.failure_window)
        # Check threshold
        count = await self.redis.zcard(self._failures_key)
        if count >= self.failure_threshold:
            await self.redis.set(self._state_key, CircuitState.OPEN)
            await self.redis.set(self._open_since_key, str(now))

    def get_score(self) -> float:
        # This is also tricky because it's sync.
        # We might need to make it async or use a cached value.
        return 1.0 # Default to 1.0, RoutingEngine will call can_execute later

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider_name,
            "state": "REDIS_BACKED",
            "score": 1.0,
        }
