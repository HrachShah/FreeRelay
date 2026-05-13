"""
FreeRelay Data Plane — Fanout Strategy
==========================================
Fire to N providers in parallel, collect all responses.
"""

from __future__ import annotations

import asyncio
import time

from freerelay.data_plane.execution.dag_engine import (
    ExecutionContext,
    StepDefinition,
    StepOutput,
    StepStatus,
    register_strategy,
)


@register_strategy("fanout")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Fan out to N providers in parallel, collect all responses.

    Params:
        n: Number of providers to use (default: 3)
        model_pool: List of ModelSlot dicts to choose from
    """
    request = ctx.globals.get("request")
    router = ctx.globals.get("router")
    profile = ctx.globals.get("profile")
    n = step.params.get("n", 3)

    if request is None:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No request in execution context",
        )

    try:
        from freerelay.data_plane.routing.engine import RoutingEngine

        model_pool = step.params.get("model_pool", [])

        if isinstance(router, RoutingEngine) and profile is not None:
            top_n = router.select_top_n(profile, model_pool, n=n)
        else:
            top_n = [(step.params.get("provider", ""), step.params.get("model", ""))]

        # Fan out to all providers in parallel
        async def call_provider(provider: str, model: str) -> StepOutput:
            start = time.monotonic()
            try:
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
                        latency_ms=(time.monotonic() - start) * 1000,
                        tokens_used=tokens,
                    )
                return StepOutput(
                    step_id=step.step_id,
                    status=StepStatus.COMPLETED,
                    provider=provider,
                    model=model,
                    latency_ms=(time.monotonic() - start) * 1000,
                )
            except (ValueError, TypeError, OSError) as e:
                return StepOutput(
                    step_id=step.step_id,
                    status=StepStatus.FAILED,
                    provider=provider,
                    model=model,
                    error=str(e),
                    latency_ms=(time.monotonic() - start) * 1000,
                )

        tasks = [call_provider(p, m) for p, m in top_n]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results
        successful = [
            r
            for r in results
            if isinstance(r, StepOutput) and r.status == StepStatus.COMPLETED
        ]

        if not successful:
            errors = [
                str(r.error) if isinstance(r, StepOutput) else str(r) for r in results
            ]
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=f"All {len(tasks)} providers failed: {'; '.join(errors[:3])}",
            )

        # Merge all successful responses
        all_contents = [r.content for r in successful if r.content]
        merged = "\n---\n".join(all_contents)
        total_tokens = sum(r.tokens_used for r in successful)

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=merged,
            provider=successful[0].provider,
            model=successful[0].model,
            tokens_used=total_tokens,
            metadata={
                "responses": [
                    {"provider": r.provider, "model": r.model, "content": r.content}
                    for r in successful
                ],
                "total_attempted": len(tasks),
                "total_succeeded": len(successful),
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
        )
