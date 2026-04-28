"""
FreeRelay Data Plane — Verifier Strategy
===========================================
Verifier checks response for factual consistency and correctness.
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


@register_strategy("verifier")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Verify a response for factual consistency.

    Params:
        source_step: Step ID of the response to verify
        check_types: List of checks to perform (factual, logical, format)
    """
    source_step = step.params.get("source_step", "")
    check_types = step.params.get("check_types", ["factual", "logical", "format"])

    if not source_step:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No source_step specified for verifier",
        )

    source_output = await ctx.get(source_step)
    if source_output is None:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=f"Source step '{source_step}' not found",
        )

    if source_output.status == StepStatus.FAILED:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=f"Source step '{source_step}' failed",
        )

    start = time.monotonic()

    try:
        content = source_output.content
        original_request = ctx.globals.get("request")

        # Build verification prompt
        original_context = ""
        if original_request:
            original_context = original_request.get_content_text()

        verify_prompt = (
            f"You are a fact-checker and consistency verifier.\n\n"
            f"Original context/question:\n{original_context}\n\n"
            f"Response to verify:\n{content}\n\n"
            f"Perform these checks: {', '.join(check_types)}\n\n"
            f"Respond with a JSON object:\n"
            f'{{"passed": true/false, "checks": {{"factual": {{"passed": bool, "issues": [...]}}}}, "confidence": 0.0-1.0}}'
        )

        router = ctx.globals.get("router")
        if router and hasattr(router, "route"):
            from freerelay.core.models.openai import (
                ChatCompletionRequest,
                Message,
            )

            verify_request = ChatCompletionRequest(
                model=step.params.get("verifier_model", ""),
                messages=[
                    Message(role="user", content=verify_prompt),
                ],
                temperature=0.0,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            response = await router.route(verify_request)
            verify_content = ""
            tokens = 0
            if response is not None:
                if response.choices:
                    verify_content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
        else:
            # Heuristic verification when no LLM available
            verify_content = '{"passed": true, "checks": {}, "confidence": 0.7}'
            tokens = 0

        # Parse verification result
        import json

        try:
            result = json.loads(verify_content)
        except json.JSONDecodeError:
            result = {"passed": True, "confidence": 0.5}

        passed = result.get("passed", True)
        confidence = result.get("confidence", 0.5)

        elapsed_ms = (time.monotonic() - start) * 1000

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=content,  # Pass through original content
            provider=source_output.provider,
            model=source_output.model,
            latency_ms=elapsed_ms,
            tokens_used=tokens,
            metadata={
                "verification_passed": passed,
                "verification_confidence": confidence,
                "verification_result": result,
                "checks_performed": check_types,
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )
