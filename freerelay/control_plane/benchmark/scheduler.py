"""
FreeRelay — Benchmark Scheduler
==================================
APScheduler-based scheduling for benchmark runs:
- Nightly full suite at 2 AM UTC
- Hourly spot checks (10% sample)
"""

from __future__ import annotations

import logging
import asyncio
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

DEFAULT_PROVIDERS = [
    ("groq", "llama-3.1-70b-versatile"),
    ("google", "gemini-2.0-flash"),
    ("openrouter", "meta-llama/llama-3.1-70b-instruct"),
    ("together", "meta-llama/Llama-3.1-70B-Instruct-Turbo"),
    ("mistral", "mistral-large-latest"),
]


class BenchmarkScheduler:
    """
    Manages scheduled benchmark runs using APScheduler.

    Jobs:
    - Nightly full suite at 2 AM UTC for all providers
    - Hourly spot check (10% sample) for all providers
    """

    def __init__(
        self,
        engine: Any,
        providers: list[tuple[str, str]] | None = None,
    ) -> None:
        self._engine = engine
        self._providers = providers or DEFAULT_PROVIDERS
        self._scheduler: AsyncIOScheduler | None = None

    def start(self) -> None:
        """Start the scheduler with configured jobs."""
        self._scheduler = AsyncIOScheduler(timezone="UTC")

        # Nightly full suite at 2 AM UTC
        self._scheduler.add_job(
            self._run_full_suite,
            trigger=CronTrigger(hour=2, minute=0, timezone="UTC"),
            id="nightly_full_suite",
            name="Nightly Full Benchmark Suite",
            replace_existing=True,
            max_instances=1,
        )

        # Hourly spot check
        self._scheduler.add_job(
            self._run_spot_check,
            trigger=IntervalTrigger(hours=1, timezone="UTC"),
            id="hourly_spot_check",
            name="Hourly Spot Check",
            replace_existing=True,
            max_instances=1,
        )

        self._scheduler.start()
        logger.info(
            "benchmark_scheduler_started jobs=%d providers=%d",
            len(self._scheduler.get_jobs()),
            len(self._providers),
        )

    def stop(self) -> None:
        """Shut down the scheduler."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("benchmark_scheduler_stopped")

    async def _run_full_suite(self) -> None:
        """Execute the full benchmark suite for all providers."""
        logger.info("scheduled_full_suite_start providers=%d", len(self._providers))
        for provider, model in self._providers:
            try:
                result = await self._engine.run_suite(
                    provider=provider,
                    model=model,
                    spot_check=False,
                )
                logger.info(
                    "full_suite_done provider=%s model=%s pass_rate=%.2f",
                    provider,
                    model,
                    result.passed_prompts / max(result.total_prompts, 1),
                )
            except (TimeoutError, asyncio.CancelledError):
                logger.exception(
                    "full_suite_error provider=%s model=%s", provider, model
                )
        logger.info("scheduled_full_suite_complete")

    async def _run_spot_check(self) -> None:
        """Execute spot check (10% sample) for all providers."""
        logger.info("scheduled_spot_check_start providers=%d", len(self._providers))
        for provider, model in self._providers:
            try:
                result = await self._engine.run_suite(
                    provider=provider,
                    model=model,
                    spot_check=True,
                )
                logger.info(
                    "spot_check_done provider=%s model=%s pass_rate=%.2f",
                    provider,
                    model,
                    result.passed_prompts / max(result.total_prompts, 1),
                )
            except (TimeoutError, asyncio.CancelledError):
                logger.exception(
                    "spot_check_error provider=%s model=%s", provider, model
                )
        logger.info("scheduled_spot_check_complete")

    async def trigger_full_suite_now(self) -> None:
        """Manually trigger a full suite run immediately."""
        logger.info("manual_full_suite_triggered")
        await self._run_full_suite()

    async def trigger_spot_check_now(self) -> None:
        """Manually trigger a spot check immediately."""
        logger.info("manual_spot_check_triggered")
        await self._run_spot_check()

    def get_scheduled_jobs(self) -> list[dict[str, Any]]:
        """Return info about all scheduled jobs."""
        if not self._scheduler:
            return []
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in self._scheduler.get_jobs()
        ]
