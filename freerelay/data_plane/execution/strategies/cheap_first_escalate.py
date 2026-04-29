"""
FreeRelay Data Plane — Cheap First Escalate Strategy
======================================================
Try cheapest provider first. If quality < threshold, escalate to strongest.
"""

from __future__ import annotations

import time

from freerelay.data_plane.execution.dag_engine import (
    ExecutionContext,
    StepDefinition,
    StepOutput,
    StepStatus,
    register_strategy,
)


@register_strategy("cheap_first_escalate")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Try cheapest provider first, escalate if quality is insufficient.

    Params:
        quality_threshold: Minimum quality score to accept (default: 0.7)
        model_pool: List of ModelSlot dicts
    """
    request = ctx.globals.get("request")
    router = ctx.globals.get("router")
    profile = ctx.globals.get("profile")
    quality_threshold = step.params.get("quality_threshold", 0.7)

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

        # Phase 1: Try cheapest
        if isinstance(router, RoutingEngine) and profile is not None:
            provider, model = router.select_cheapest(profile, model_pool)
        else:
            provider = step.params.get("provider", "")
            model = step.params.get("model", "")

        if not provider:
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error="No providers available",
            )

        # Execute with cheapest
        if hasattr(router, "route"):
            response = await router.route(request)
            content = ""
            tokens = 0
            if response is not None and response.choices:
                content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response is not None and response.usage else 0
        else:
            content = ""
            tokens = 0

        # Simple quality heuristic
        quality_score = _estimate_quality(content)

        if quality_score >= quality_threshold:
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                content=content,
                provider=provider,
                model=model,
                latency_ms=(time.monotonic() - start) * 1000,
                tokens_used=tokens,
                metadata={"phase": "cheap", "quality_score": quality_score},
            )

        # Phase 2: Escalate to strongest
        if isinstance(router, RoutingEngine) and profile is not None:
            provider2, model2 = router.select_strongest(profile, model_pool)
        else:
            provider2 = provider
            model2 = model

        if hasattr(router, "route"):
            response2 = await router.route(request)
            content2 = ""
            tokens2 = 0
            if response2 is not None and response2.choices:
                content2 = response2.choices[0].message.content or ""
            tokens2 = response2.usage.total_tokens if response2 is not None and response2.usage else 0
        else:
            content2 = content
            tokens2 = tokens

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=content2,
            provider=provider2,
            model=model2,
            latency_ms=(time.monotonic() - start) * 1000,
            tokens_used=tokens + tokens2,
            metadata={
                "phase": "escalated",
                "cheap_provider": provider,
                "cheap_quality": quality_score,
                "threshold": quality_threshold,
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )


def _estimate_quality(content: str) -> float:
    """
    Simple quality heuristic based on response characteristics.
    Returns a score between 0.0 and 1.0.
    """
    if not content:
        return 0.0

    score = 0.5  # Base score

    # Length-based: very short or very long responses may be poor
    length = len(content)
    if 100 < length < 5000:
        score += 0.1

    # Sentence structure
    sentences = content.count(".") + content.count("!") + content.count("?")
    if sentences >= 2:
        score += 0.1

    # No obvious error patterns
    error_patterns = ["i'm sorry", "i cannot", "as an ai", "error:", "failed"]
    content_lower = content.lower()
    if not any(p in content_lower for p in error_patterns):
        score += 0.1

    # Has some substantive content
    words = content.split()
    if len(words) >= 20:
        score += 0.1

    return min(1.0, score)
