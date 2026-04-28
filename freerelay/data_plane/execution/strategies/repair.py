"""
FreeRelay Data Plane — Repair Strategy
=========================================
Repair model receives original request + failed response + failure reason.
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


@register_strategy("repair")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Repair a failed or invalid response.

    Params:
        source_step: Step ID of the response to repair
        failure_reason: Description of what went wrong
        repair_instructions: Specific instructions for the repair
    """
    source_step = step.params.get("source_step", "")
    failure_reason = step.params.get("failure_reason", "Response validation failed")
    repair_instructions = step.params.get("repair_instructions", "")

    if not source_step:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No source_step specified for repair",
        )

    source_output = await ctx.get(source_step)
    if source_output is None:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=f"Source step '{source_step}' not found",
        )

    start = time.monotonic()

    try:
        original_content = source_output.content
        original_request = ctx.globals.get("request")

        # Build repair prompt
        original_context = ""
        if original_request:
            original_context = original_request.get_content_text()

        repair_prompt = (
            f"You are a repair agent. The following response has issues that need fixing.\n\n"
            f"Original request:\n{original_context}\n\n"
            f"Failed response:\n{original_content}\n\n"
            f"Failure reason: {failure_reason}\n"
        )

        if repair_instructions:
            repair_prompt += f"\nRepair instructions: {repair_instructions}\n"

        repair_prompt += (
            "\nProvide the corrected response. Output ONLY the corrected content, "
            "no explanations or commentary."
        )

        router = ctx.globals.get("router")
        if router and hasattr(router, "route"):
            from freerelay.core.models.openai import (
                ChatCompletionRequest,
                Message,
            )

            repair_request = ChatCompletionRequest(
                model=step.params.get("repair_model", ""),
                messages=[
                    Message(role="user", content=repair_prompt),
                ],
                temperature=0.0,
                max_tokens=4096,
            )
            response = await router.route(repair_request)
            repaired_content = ""
            tokens = 0
            if response is not None:
                if response.choices:
                    repaired_content = response.choices[0].message.content or ""
                if response.usage:
                    tokens = response.usage.total_tokens
        else:
            repaired_content = original_content
            tokens = 0

        elapsed_ms = (time.monotonic() - start) * 1000

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=repaired_content,
            provider=source_output.provider,
            model=source_output.model,
            latency_ms=elapsed_ms,
            tokens_used=tokens,
            metadata={
                "original_content": original_content,
                "failure_reason": failure_reason,
                "repair_applied": repaired_content != original_content,
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )
