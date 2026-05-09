"""Control Plane entrypoint. Leader election + 60s tick loop."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import signal
import time
import uuid
from typing import Any

import redis.asyncio as aioredis

from freerelay.config.settings import get_settings

logger = logging.getLogger(__name__)

LEADER_KEY = "freerelay:cp:leader"
LEADER_TTL = 30  # seconds
TICK_INTERVAL = 60  # seconds


class ControlPlane:
    """Manages policy learning, benchmarking, and anomaly detection."""

    def __init__(self, redis_url: str | None = None) -> None:
        settings = get_settings()
        self._redis_url = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None
        self._instance_id = str(uuid.uuid4())
        self._is_leader = False
        self._running = False
        self._tick_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the control plane with leader election."""
        self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        self._running = True
        logger.info("control_plane_starting instance=%s", self._instance_id)

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        await self._leader_loop()

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self._tick_task and not self._tick_task.done():
            self._tick_task.cancel()
        if self._redis:
            # Release leadership
            current = await self._redis.get(LEADER_KEY)
            if current == self._instance_id:
                await self._redis.delete(LEADER_KEY)
            await self._redis.aclose()
        logger.info("control_plane_stopped instance=%s", self._instance_id)

    async def _leader_loop(self) -> None:
        """Main loop: try to become leader, run ticks if leader."""
        while self._running:
            if not self._is_leader:
                await self._try_acquire_leadership()
            if self._is_leader:
                await self._renew_leadership()
                if self._tick_task is None or self._tick_task.done():
                    self._tick_task = asyncio.create_task(self._run_tick())
            await asyncio.sleep(5)

    async def _try_acquire_leadership(self) -> None:
        """Attempt to acquire leadership via Redis SETNX."""
        assert self._redis is not None
        acquired = await self._redis.set(
            LEADER_KEY, self._instance_id, nx=True, ex=LEADER_TTL
        )
        if acquired:
            self._is_leader = True
            logger.info("leadership_acquired instance=%s", self._instance_id)

    async def _renew_leadership(self) -> None:
        """Renew leadership lease."""
        assert self._redis is not None
        current = await self._redis.get(LEADER_KEY)
        if current == self._instance_id:
            await self._redis.expire(LEADER_KEY, LEADER_TTL)
        else:
            self._is_leader = False
            logger.warning("leadership_lost instance=%s", self._instance_id)

    async def _run_tick(self) -> None:
        """60-second tick: consume outcomes, update bandit, publish policy."""
        assert self._redis is not None
        try:
            logger.info("tick_start instance=%s", self._instance_id)
            tick_start = time.monotonic()

            # Step 1: Consume outcome records from Redis Stream
            outcomes = await self._consume_outcomes()
            logger.info("tick_outcomes_consumed count=%d", len(outcomes))

            # Step 2: Update bandit arms from outcomes
            if outcomes:
                await self._update_bandit_arms(outcomes)

            # Step 3: Run anomaly detection
            await self._run_anomaly_detection()

            # Step 4: Publish updated policy
            await self._publish_policy()

            elapsed = time.monotonic() - tick_start
            logger.info("tick_complete elapsed=%.2fs", elapsed)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("tick_error")
        finally:
            # Sleep remainder of tick interval
            await asyncio.sleep(TICK_INTERVAL)

    async def _consume_outcomes(self) -> list[dict[str, Any]]:
        """Consume outcome records from Redis Stream."""
        assert self._redis is not None
        outcomes: list[dict[str, Any]] = []
        try:
            # Read from stream using consumer group
            results = await self._redis.xreadgroup(
                groupname="control-plane-learner",
                consumername=self._instance_id,
                streams={"freerelay:outcomes": ">"},
                count=100,
                block=1000,
            )
            for _stream_name, messages in results:
                for msg_id, fields in messages:
                    outcomes.append({"id": msg_id, **fields})
                    # Acknowledge
                    try:
                        await self._redis.xack(
                            "freerelay:outcomes", "control-plane-learner", msg_id
                        )
                    except (redis.ResponseError, redis.ConnectionError):
                        logger.exception("consume_outcomes_error")
        except (redis.ResponseError, redis.ConnectionError):
            logger.exception("consume_outcomes_error")
        return outcomes

    async def _update_bandit_arms(self, outcomes: list[dict[str, Any]]) -> None:
        """Update UCB bandit arms from outcome records."""
        assert self._redis is not None

        for outcome in outcomes:
            try:
                provider = outcome.get("provider_chosen", "")
                model = outcome.get("model_chosen", "")
                task_family = outcome.get("task_family", "general")
                if not provider or not model:
                    continue

                key = f"freerelay:bandit:{provider}:{model}:{task_family}"
                arm_data = await self._redis.hgetall(key)

                # Compute quality signal
                output_valid = float(outcome.get("output_valid", 0))
                judge_score = float(outcome.get("judge_score", 0.5))
                repair_triggered = float(outcome.get("repair_triggered", 0))
                client_retried = float(outcome.get("client_retried", 0))
                client_regenerated = float(outcome.get("client_regenerated", 0))

                quality_signal = (
                    0.4 * output_valid
                    + 0.3 * judge_score
                    + 0.15 * (1.0 - repair_triggered)
                    + 0.1 * (1.0 - client_retried)
                    + 0.05 * (1.0 - client_regenerated)
                )

                n_pulls = int(arm_data.get("n_pulls", 0))
                mean_quality = float(arm_data.get("mean_quality", 0.5))
                ewma_quality = float(arm_data.get("ewma_quality", 0.5))

                # EWMA update
                alpha = 0.1 if n_pulls > 100 else 0.3
                new_ewma = alpha * quality_signal + (1 - alpha) * ewma_quality

                # Welford's online mean
                n_pulls += 1
                delta = quality_signal - mean_quality
                new_mean = mean_quality + delta / n_pulls

                await self._redis.hset(
                    key,
                    mapping={
                        "mean_quality": str(new_mean),
                        "n_pulls": str(n_pulls),
                        "ewma_quality": str(new_ewma),
                        "last_updated_ts": str(time.time()),
                    },
                )

            except Exception:
                logger.exception(
                    "bandit_update_error provider=%s", outcome.get("provider_chosen")
                )

    async def _run_anomaly_detection(self) -> None:
        """Run EWMA control limit anomaly detection on provider metrics."""
        assert self._redis is not None

        providers = await self._redis.keys("freerelay:capability:*")
        for key in providers:
            try:
                parts = key.split(":")
                if len(parts) < 3:
                    continue
                provider = parts[2]

                # Check latency metrics
                latency_key = f"freerelay:anomaly:{provider}:latency"
                history = await self._redis.lrange(latency_key, 0, -1)
                if len(history) < 10:
                    continue

                values = [float(v) for v in history]
                new_value = values[-1]
                alpha = 0.2

                ewma = values[0]
                for v in values[1:]:
                    ewma = alpha * v + (1 - alpha) * ewma

                ewma_var = 0.0
                for v in values[1:]:
                    ewma_var = alpha * (v - ewma) ** 2 + (1 - alpha) * ewma_var

                sigma = math.sqrt(max(ewma_var, 1e-10))
                upper = ewma + 3 * sigma
                lower = ewma - 3 * sigma

                if new_value > upper or new_value < lower:
                    severity = abs(new_value - ewma) / sigma if sigma > 0 else 0
                    logger.warning(
                        "anomaly_detected provider=%s metric=latency value=%.2f ewma=%.2f severity=%.2f",
                        provider,
                        new_value,
                        ewma,
                        severity,
                    )
                    # Set degradation flag
                    await self._redis.hset(
                        f"freerelay:capability:{provider}",
                        "latency_degraded",
                        "1",
                    )

            except Exception:
                logger.exception("anomaly_detection_error key=%s", key)

    async def _publish_policy(self) -> None:
        """Publish current routing policy to Redis Pub/Sub channel."""
        assert self._redis is not None

        try:
            # Load current policy from Redis
            policy_str = await self._redis.get("freerelay:policy:v2")
            if policy_str:
                policy = json.loads(policy_str)
                policy["version_ts"] = time.time()
                await self._redis.set("freerelay:policy:v2", json.dumps(policy))
                await self._redis.publish("freerelay:policy:v2", json.dumps(policy))
                logger.info(
                    "policy_published version=%s", policy.get("version", "unknown")
                )
        except Exception:
            logger.exception("policy_publish_error")


async def run_control_plane(redis_url: str | None = None) -> None:
    """Entry point for running the control plane."""
    cp = ControlPlane(redis_url=redis_url)
    await cp.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    asyncio.run(run_control_plane())
