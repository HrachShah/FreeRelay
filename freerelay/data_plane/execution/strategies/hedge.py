"""
FreeRelay Data Plane — Hedge Strategy
========================================
Top 2 providers, first-completed wins, cancel other.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from freerelay.data_plane.execution.dag_engine import (
    ExecutionContext,
    StepDefinition,
    StepOutput,
    StepStatus,
    register_strategy,
)


@register_strategy("hedge")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Hedge: send to top 2 providers, first response wins.

    Params:
        delay_ms: Delay before sending to second provider (default: 0)
        model_pool: List of ModelSlot dicts
    """
    request = ctx.globals.get("request")
    router = ctx.globals.get("router")
    profile = ctx.globals.get("profile")
    delay_ms = step.params.get("delay_ms", 0)

    if request is None:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No request in execution context",
        )

    start = time.monotonic()

    try:
        from freerelay.data_plane.routing.engine import RoutingEngine

        model_pool = step.params.get("model_pool", [])

        if isinstance(router, RoutingEngine) and profile is not None:
            top_2 = router.select_top_n(profile, model_pool, n=2)
        else:
            p = step.params.get("provider", "")
            m = step.params.get("model", "")
            top_2 = [(p, m)]

        if len(top_2) < 2:
            # Only one provider, use single strategy
            provider, model = top_2[0] if top_2 else ("", "")
            if hasattr(router, "route"):
                response = await router.route(request)
                content = ""
                tokens = 0
                if response.choices:
                    content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
            else:
                content = ""
                tokens = 0

            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                content=content,
                provider=provider,
                model=model,
                latency_ms=(time.monotonic() - start) * 1000,
                tokens_used=tokens,
            )

        # Hedged execution
        winner: StepOutput | None = None

        async def race_provider(provider: str, model: str) -> StepOutput:
            p_start = time.monotonic()
            if hasattr(router, "route"):
                response = await router.route(request)
                content = ""
                tokens = 0
                if response.choices:
                    content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return StepOutput(
                    step_id=step.step_id,
                    status=StepStatus.COMPLETED,
                    content=content,
                    provider=provider,
                    model=model,
                    latency_ms=(time.monotonic() - p_start) * 1000,
                    tokens_used=tokens,
                )
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                provider=provider,
                model=model,
                latency_ms=(time.monotonic() - p_start) * 1000,
            )

        async def delayed_race(provider: str, model: str) -> StepOutput:
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
            return await race_provider(provider, model)

        # Race both providers
        task1 = asyncio.create_task(race_provider(top_2[0][0], top_2[0][1]))
        task2 = asyncio.create_task(delayed_race(top_2[1][0], top_2[1][1]))

        done, pending = await asyncio.wait(
            [task1, task2],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Get the winner
        for task in done:
            try:
                result = task.result()
                if result.status == StepStatus.COMPLETED:
                    winner = result
                    break
            except Exception:
                continue

        # Cancel pending tasks
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

        if winner is None:
            # Both failed, try to get errors
            errors = []
            for task in [task1, task2]:
                try:
                    r = task.result()
                    if r.error:
                        errors.append(r.error)
                except Exception as e:
                    errors.append(str(e))

            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=f"Both hedged providers failed: {'; '.join(errors)}",
                latency_ms=(time.monotonic() - start) * 1000,
            )

        winner.latency_ms = (time.monotonic() - start) * 1000
        winner.metadata["hedge"] = True
        winner.metadata["hedge_delay_ms"] = delay_ms
        return winner

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )
