"""
FreeRelay — Drift / Anomaly Detector
========================================
EWMA control-limit anomaly detection for provider metrics.
Runs on a 5-minute tick and sets degradation flags when anomalies are detected.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

ANOMALY_KEY_PREFIX = "freerelay:anomaly"
DETECTION_ALPHA = 0.2  # EWMA smoothing factor
SIGMA_MULTIPLIER = 3.0  # 3-sigma control limits
MIN_SAMPLES = 10  # minimum data points before detection activates


@dataclass
class AnomalyResult:
    """Result of anomaly detection on a single metric."""

    is_anomaly: bool
    severity: float  # absolute deviations from EWMA in sigma units
    ewma: float
    sigma: float
    value: float
    upper_limit: float
    lower_limit: float
    provider: str = ""
    metric: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_anomaly": self.is_anomaly,
            "severity": self.severity,
            "ewma": self.ewma,
            "sigma": self.sigma,
            "value": self.value,
            "upper_limit": self.upper_limit,
            "lower_limit": self.lower_limit,
            "provider": self.provider,
            "metric": self.metric,
            "timestamp": self.timestamp,
        }


def compute_ewma_sigma(
    values: list[float], alpha: float = DETECTION_ALPHA
) -> tuple[float, float]:
    """
    Compute EWMA and EWMA-based standard deviation from a series.

    Returns (ewma, sigma).
    """
    if not values:
        return 0.0, 0.0

    ewma = values[0]
    ewma_var = 0.0

    for v in values[1:]:
        ewma = alpha * v + (1 - alpha) * ewma
        ewma_var = alpha * (v - ewma) ** 2 + (1 - alpha) * ewma_var

    sigma = math.sqrt(max(ewma_var, 1e-10))
    return ewma, sigma


def detect_anomaly(
    values: list[float],
    new_value: float,
    alpha: float = DETECTION_ALPHA,
    sigma_multiplier: float = SIGMA_MULTIPLIER,
    min_samples: int = MIN_SAMPLES,
) -> AnomalyResult:
    """
    Detect if a new value is anomalous using EWMA control limits.

    Uses exponentially-weighted moving average with 3-sigma bounds.

    Args:
        values: Historical values (last entry is the new value if already appended).
        new_value: The value to test for anomaly.
        alpha: EWMA smoothing factor (0 < alpha <= 1).
        sigma_multiplier: Number of standard deviations for control limits.
        min_samples: Minimum historical samples required before detection activates.

    Returns:
        AnomalyResult with detection outcome and diagnostics.
    """
    # Filter to just historical values (exclude the new value if present)
    history = (
        [v for v in values if v != new_value] if new_value in values else list(values)
    )
    if not history:
        history = values

    if len(history) < min_samples:
        return AnomalyResult(
            is_anomaly=False,
            severity=0.0,
            ewma=new_value,
            sigma=0.0,
            value=new_value,
            upper_limit=float("inf"),
            lower_limit=float("-inf"),
        )

    ewma, sigma = compute_ewma_sigma(history, alpha=alpha)
    upper = ewma + sigma_multiplier * sigma
    lower = ewma - sigma_multiplier * sigma

    is_anomaly = new_value > upper or new_value < lower
    severity = abs(new_value - ewma) / sigma if sigma > 0 else 0.0

    return AnomalyResult(
        is_anomaly=is_anomaly,
        severity=severity,
        ewma=ewma,
        sigma=sigma,
        value=new_value,
        upper_limit=upper,
        lower_limit=lower,
    )


class DriftDetector:
    """
    Periodic anomaly detection on provider metrics.

    Reads metric histories from Redis lists and flags anomalies
    by setting degradation flags in the capability registry.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def detect_provider_metric(
        self,
        provider: str,
        metric: str,
        new_value: float | None = None,
    ) -> AnomalyResult:
        """
        Run anomaly detection on a specific provider metric.

        Args:
            provider: Provider name.
            metric: Metric name (e.g., 'latency', 'error_rate').
            new_value: If provided, test this value; otherwise use last in history.

        Returns:
            AnomalyResult.
        """
        history_key = f"{ANOMALY_KEY_PREFIX}:{provider}:{metric}"

        try:
            raw_history = await self._redis.lrange(history_key, 0, -1)
            values = [float(v) for v in raw_history]
        except (ValueError, OSError) as e:
            logger.exception(
                "detect_read_error provider=%s metric=%s", provider, metric
            )
            return AnomalyResult(
                is_anomaly=False,
                severity=0.0,
                ewma=0.0,
                sigma=0.0,
                value=0.0,
                upper_limit=float("inf"),
                lower_limit=float("-inf"),
                provider=provider,
                metric=metric,
            )

        if new_value is None:
            if not values:
                return AnomalyResult(
                    is_anomaly=False,
                    severity=0.0,
                    ewma=0.0,
                    sigma=0.0,
                    value=0.0,
                    upper_limit=float("inf"),
                    lower_limit=float("-inf"),
                    provider=provider,
                    metric=metric,
                )
            new_value = values[-1]
            values = values[:-1]

        result = detect_anomaly(values, new_value)
        result.provider = provider
        result.metric = metric

        if result.is_anomaly:
            logger.warning(
                "anomaly_detected provider=%s metric=%s value=%.2f ewma=%.2f sigma=%.2f severity=%.2f",
                provider,
                metric,
                result.value,
                result.ewma,
                result.sigma,
                result.severity,
            )
            await self._set_degradation(provider, metric, True)
        else:
            # Clear degradation if within normal bounds
            await self._set_degradation(provider, metric, False)

        return result

    async def detect_all_providers(
        self,
        metrics: list[str] | None = None,
    ) -> list[AnomalyResult]:
        """
        Run anomaly detection across all providers for specified metrics.

        Args:
            metrics: List of metric names to check. Defaults to ['latency', 'error_rate'].

        Returns:
            List of AnomalyResult for all (provider, metric) combinations.
        """
        if metrics is None:
            metrics = ["latency", "error_rate"]

        results: list[AnomalyResult] = []

        try:
            # Discover all providers from anomaly key patterns
            provider_keys = await self._redis.keys(f"{ANOMALY_KEY_PREFIX}:*")
            providers: set[str] = set()
            for key in provider_keys:
                parts = key.split(":")
                if len(parts) >= 3:
                    providers.add(parts[2])

            for provider in providers:
                for metric in metrics:
                    result = await self.detect_provider_metric(provider, metric)
                    results.append(result)

        except Exception:
            logger.exception("detect_all_error")

        return results

    async def append_metric_value(
        self,
        provider: str,
        metric: str,
        value: float,
        max_history: int = 1000,
    ) -> None:
        """
        Append a new metric value to the history list.

        Args:
            provider: Provider name.
            metric: Metric name.
            value: The metric value.
            max_history: Maximum history entries to keep.
        """
        key = f"{ANOMALY_KEY_PREFIX}:{provider}:{metric}"
        try:
            pipe = self._redis.pipeline()
            pipe.lpush(key, str(value))
            pipe.ltrim(key, 0, max_history - 1)
            await pipe.execute()
        except OSError as e:
            logger.exception(
                "append_metric_error provider=%s metric=%s", provider, metric
            )

    async def _set_degradation(
        self, provider: str, metric: str, is_degraded: bool
    ) -> None:
        """Set degradation flag in the capability registry."""
        flag_field = f"{metric}_degraded"
        try:
            # Find all capability keys for this provider
            cap_keys = await self._redis.keys(f"freerelay:capability:{provider}:*")
            for cap_key in cap_keys:
                await self._redis.hset(cap_key, flag_field, str(is_degraded))
                if is_degraded:
                    await self._redis.hset(
                        cap_key, "last_degraded_at", str(time.time())
                    )
        except Exception:
            logger.exception(
                "set_degradation_error provider=%s metric=%s", provider, metric
            )

    async def get_metric_history(
        self,
        provider: str,
        metric: str,
        count: int = 100,
    ) -> list[float]:
        """Retrieve recent metric history values."""
        key = f"{ANOMALY_KEY_PREFIX}:{provider}:{metric}"
        try:
            raw = await self._redis.lrange(key, 0, count - 1)
            return [float(v) for v in raw]
        except Exception:
            logger.exception(
                "get_history_error provider=%s metric=%s", provider, metric
            )
            return []

    async def clear_history(self, provider: str, metric: str | None = None) -> None:
        """Clear metric history for a provider (or specific metric)."""
        if metric:
            key = f"{ANOMALY_KEY_PREFIX}:{provider}:{metric}"
            await self._redis.delete(key)
        else:
            keys = await self._redis.keys(f"{ANOMALY_KEY_PREFIX}:{provider}:*")
            if keys:
                await self._redis.delete(*keys)
        logger.info("anomaly_history_cleared provider=%s metric=%s", provider, metric)
