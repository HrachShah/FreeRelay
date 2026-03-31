"""
FreeRelay Data Plane — Single Strategy
==========================================
Route to one provider using expected utility scoring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from freerelay.data_plane.execution.dag_engine import (
    ExecutionContext,
    StepDefinition,
    StepOutput,
    StepStatus,
    register_strategy,
)

if TYPE_CHECKING:
    pass


@register_strategy("single")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Route to a single provider using expected utility.

    Uses the router from the execution context globals to select
    the best provider/model for the request.
    """
    request = ctx.globals.get("request")
    router = ctx.globals.get("router")
    profile = ctx.globals.get("profile")

    if request is None:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No request in execution context",
        )

    if router is None:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No router in execution context",
        )

    try:
        from freerelay.data_plane.routing.engine import RoutingEngine

        if isinstance(router, RoutingEngine):
            decision = router.select(profile, step.params.get("model_pool", []))
            provider = decision.selected_provider
            model = decision.selected_model
        else:
            provider = step.params.get("provider", "")
            model = step.params.get("model", "")

        # Execute the request through the selected provider
        # In production this calls the provider's complete() method
        start_import = __import__("time").monotonic()

        # Simulate provider execution (replaced by actual provider call)
        content = ""
        tokens = 0

        if hasattr(router, "route"):
            response = await router.route(request)
            if response.choices:
                content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0

        elapsed_ms = (__import__("time").monotonic() - start_import) * 1000

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=content,
            provider=provider,
            model=model,
            latency_ms=elapsed_ms,
            tokens_used=tokens,
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
        )
