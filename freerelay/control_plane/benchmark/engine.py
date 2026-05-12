"""
FreeRelay — Benchmark Engine
===============================
Orchestrates benchmark runs against providers. Collects performance metrics
and stores results in Redis sorted sets for analysis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

from freerelay.control_plane.benchmark.evaluator import ScoreResult, evaluate
from freerelay.control_plane.benchmark.suite import (
    BenchmarkPrompt,
    BenchmarkType,
    get_spot_sample,
    load_suite,
)

logger = logging.getLogger(__name__)

RESULTS_KEY_PREFIX = "freerelay:benchmark:results"
MAX_CONCURRENT_PER_PROVIDER = 5
DEFAULT_TIMEOUT_S = 30.0


@dataclass
class BenchmarkRunResult:
    """Result of running a single benchmark prompt against a provider."""

    prompt_id: str
    benchmark_type: BenchmarkType
    provider: str
    model: str
    score: float
    passed: bool
    ttft_ms: float  # time to first token
    total_latency_ms: float
    tokens_per_second: float
    schema_compliant: bool
    quality_score: float
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "benchmark_type": self.benchmark_type.value,
            "provider": self.provider,
            "model": self.model,
            "score": self.score,
            "passed": self.passed,
            "ttft_ms": self.ttft_ms,
            "total_latency_ms": self.total_latency_ms,
            "tokens_per_second": self.tokens_per_second,
            "schema_compliant": self.schema_compliant,
            "quality_score": self.quality_score,
            "error": self.error,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class BenchmarkSuiteResult:
    """Aggregate result of a full or spot-check benchmark run."""

    provider: str
    model: str
    suite_name: str
    results: list[BenchmarkRunResult]
    start_time: float
    end_time: float
    total_prompts: int
    passed_prompts: int
    mean_score: float
    mean_ttft_ms: float
    mean_latency_ms: float
    mean_tokens_per_sec: float
    schema_compliance_rate: float

    @property
    def duration_s(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "suite_name": self.suite_name,
            "total_prompts": self.total_prompts,
            "passed_prompts": self.passed_prompts,
            "pass_rate": self.passed_prompts / max(self.total_prompts, 1),
            "mean_score": self.mean_score,
            "mean_ttft_ms": self.mean_ttft_ms,
            "mean_latency_ms": self.mean_latency_ms,
            "mean_tokens_per_sec": self.mean_tokens_per_sec,
            "schema_compliance_rate": self.schema_compliance_rate,
            "duration_s": self.duration_s,
            "results": [r.to_dict() for r in self.results],
        }


class BenchmarkEngine:
    """
    Orchestrates benchmark execution against LLM providers.

    Supports full suite and spot-check (10% sample) modes.
    Stores results in Redis sorted sets keyed by freerelay:benchmark:results:{provider}:{model}:{suite}.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        provider_caller: Any | None = None,
    ) -> None:
        self._redis = redis_client
        self._provider_caller = provider_caller
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    def _get_semaphore(self, provider: str) -> asyncio.Semaphore:
        """Get or create a concurrency-limiting semaphore per provider."""
        if provider not in self._semaphores:
            self._semaphores[provider] = asyncio.Semaphore(MAX_CONCURRENT_PER_PROVIDER)
        return self._semaphores[provider]

    async def run_suite(
        self,
        provider: str,
        model: str,
        spot_check: bool = False,
        suite_dir: str | None = None,
    ) -> BenchmarkSuiteResult:
        """
        Run the benchmark suite against a provider/model.

        Args:
            provider: Provider name (e.g., 'groq', 'google').
            model: Model identifier.
            spot_check: If True, run only 10% sample.
            suite_dir: Optional custom suite directory.

        Returns:
            BenchmarkSuiteResult with all individual results.
        """
        prompts = load_suite(suite_dir)
        if spot_check:
            prompts = get_spot_sample(prompts)
            suite_name = "spot_check"
        else:
            suite_name = "full_suite"

        logger.info(
            "benchmark_start provider=%s model=%s suite=%s prompts=%d",
            provider,
            model,
            suite_name,
            len(prompts),
        )

        start = time.monotonic()
        results: list[BenchmarkRunResult] = []

        # Run prompts with concurrency limiting
        tasks = [self._run_single_prompt(provider, model, prompt) for prompt in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        end = time.monotonic()

        suite_result = self._aggregate_results(
            provider=provider,
            model=model,
            suite_name=suite_name,
            results=results,
            start_time=start,
            end_time=end,
        )

        # Store in Redis
        await self._store_results(suite_result)

        logger.info(
            "benchmark_complete provider=%s model=%s suite=%s pass_rate=%.2f mean_score=%.3f duration=%.1fs",
            provider,
            model,
            suite_name,
            suite_result.passed_prompts / max(suite_result.total_prompts, 1),
            suite_result.mean_score,
            suite_result.duration_s,
        )

        return suite_result

    async def _run_single_prompt(
        self,
        provider: str,
        model: str,
        prompt: BenchmarkPrompt,
    ) -> BenchmarkRunResult:
        """Run a single benchmark prompt against the provider."""
        sem = self._get_semaphore(provider)
        async with sem:
            return await self._execute_prompt(provider, model, prompt)

    async def _execute_prompt(
        self,
        provider: str,
        model: str,
        prompt: BenchmarkPrompt,
    ) -> BenchmarkRunResult:
        """Execute a prompt and evaluate the response."""
        start_time = time.monotonic()
        ttft_ms = 0.0
        output = ""
        error = None
        tokens_out = 0

        try:
            if self._provider_caller:
                # Use the real provider caller
                result = await asyncio.wait_for(
                    self._provider_caller(
                        provider=provider,
                        model=model,
                        prompt=prompt.prompt,
                        timeout=prompt.timeout_s,
                    ),
                    timeout=prompt.timeout_s + 5,
                )
                output = result.get("output", "")
                ttft_ms = result.get("ttft_ms", 0.0)
                tokens_out = result.get("tokens_out", 0)
            else:
                # Placeholder: no provider caller configured
                output = f"[placeholder response for {prompt.id}]"
                ttft_ms = 50.0
                tokens_out = len(output.split())

        except TimeoutError:
            error = f"Timeout after {prompt.timeout_s}s"
        except Exception as exc:
            error = str(exc)

        end_time = time.monotonic()
        total_latency_ms = (end_time - start_time) * 1000
        elapsed_s = end_time - start_time
        tokens_per_second = tokens_out / max(elapsed_s, 0.001)

        # Evaluate output
        if error:
            eval_result = ScoreResult(score=0.0, passed=False, error=error)
        else:
            eval_result = evaluate(
                output=output,
                benchmark_type=prompt.type,
                reference=prompt.reference_answer,
                schema=prompt.schema,
            )

        return BenchmarkRunResult(
            prompt_id=prompt.id,
            benchmark_type=prompt.type,
            provider=provider,
            model=model,
            score=eval_result.score,
            passed=eval_result.passed,
            ttft_ms=ttft_ms,
            total_latency_ms=total_latency_ms,
            tokens_per_second=tokens_per_second,
            schema_compliant=eval_result.details.get(
                "schema_valid", eval_result.details.get("parse_ok", False)
            ),
            quality_score=eval_result.score,
            error=error or eval_result.error,
            details=eval_result.details,
        )

    def _aggregate_results(
        self,
        provider: str,
        model: str,
        suite_name: str,
        results: list[BenchmarkRunResult],
        start_time: float,
        end_time: float,
    ) -> BenchmarkSuiteResult:
        """Aggregate individual results into a suite summary."""
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        mean_score = sum(r.score for r in results) / max(total, 1)
        mean_ttft = sum(r.ttft_ms for r in results) / max(total, 1)
        mean_latency = sum(r.total_latency_ms for r in results) / max(total, 1)
        mean_tps = sum(r.tokens_per_second for r in results) / max(total, 1)
        schema_compliant = sum(1 for r in results if r.schema_compliant)
        schema_rate = schema_compliant / max(total, 1)

        return BenchmarkSuiteResult(
            provider=provider,
            model=model,
            suite_name=suite_name,
            results=results,
            start_time=start_time,
            end_time=end_time,
            total_prompts=total,
            passed_prompts=passed,
            mean_score=mean_score,
            mean_ttft_ms=mean_ttft,
            mean_latency_ms=mean_latency,
            mean_tokens_per_sec=mean_tps,
            schema_compliance_rate=schema_rate,
        )

    async def _store_results(self, suite_result: BenchmarkSuiteResult) -> None:
        """Store benchmark results in Redis sorted sets."""
        try:
            key = (
                f"{RESULTS_KEY_PREFIX}:"
                f"{suite_result.provider}:"
                f"{suite_result.model}:"
                f"{suite_result.suite_name}"
            )

            # Store aggregate as sorted set entry (score = mean_score)
            aggregate_data = json.dumps(
                {
                    "mean_score": suite_result.mean_score,
                    "pass_rate": suite_result.passed_prompts
                    / max(suite_result.total_prompts, 1),
                    "mean_ttft_ms": suite_result.mean_ttft_ms,
                    "mean_latency_ms": suite_result.mean_latency_ms,
                    "schema_compliance": suite_result.schema_compliance_rate,
                    "total_prompts": suite_result.total_prompts,
                    "timestamp": suite_result.end_time,
                }
            )

            pipe = self._redis.pipeline()
            pipe.zadd(key, {aggregate_data: suite_result.end_time})
            pipe.zremrangebyrank(key, 0, -101)  # keep last 100 runs
            await pipe.execute()

            # Store individual results
            for result in suite_result.results:
                detail_key = f"{key}:details"
                detail_data = json.dumps(result.to_dict())
                await self._redis.zadd(detail_key, {detail_data: result.timestamp})
                await self._redis.zremrangebyrank(detail_key, 0, -501)  # keep last 500

            logger.info("benchmark_results_stored key=%s", key)

        except (redis.asyncio.RedisError, json.JSONDecodeError):
            logger.exception("store_results_error")

    async def get_latest_results(
        self,
        provider: str,
        model: str,
        suite_name: str = "full_suite",
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """Retrieve the latest benchmark results for a provider/model."""
        key = f"{RESULTS_KEY_PREFIX}:{provider}:{model}:{suite_name}"
        try:
            entries = await self._redis.zrevrange(key, 0, count - 1)
            return [json.loads(e) for e in entries]
        except (redis.asyncio.RedisError, json.JSONDecodeError):
            logger.exception("get_results_error")
            return []

    async def get_provider_comparison(
        self,
        suite_name: str = "full_suite",
    ) -> list[dict[str, Any]]:
        """Get latest benchmark scores across all providers for comparison."""
        try:
            pattern = f"{RESULTS_KEY_PREFIX}:*:*:{suite_name}"
            keys = []
            async for key in self._redis.scan_iter(match=pattern, count=100):
                keys.append(key)

            comparison: list[dict[str, Any]] = []
            for key in keys:
                parts = key.split(":")
                if len(parts) >= 5:
                    provider = parts[2]
                    model = parts[3]
                    latest = await self._redis.zrevrange(key, 0, 0)
                    if latest:
                        data = json.loads(latest[0])
                        data["provider"] = provider
                        data["model"] = model
                        comparison.append(data)

            return sorted(
                comparison, key=lambda x: x.get("mean_score", 0), reverse=True
            )

        except Exception:
            logger.exception("provider_comparison_error")
            return []
