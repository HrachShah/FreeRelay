"""
FreeRelay Data Plane — Judge Strategy
========================================
Judge model receives N candidates, selects best based on rubric.
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


@register_strategy("judge")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Judge model receives N candidate responses and selects the best.

    Params:
        candidates_step: Step ID that produced the candidate responses
        rubric: Evaluation criteria (default: generic quality rubric)
        judge_provider: Provider to use for the judge
    """
    candidates_step = step.params.get("candidates_step", "")
    rubric = step.params.get(
        "rubric",
        "Select the best response based on accuracy, completeness, and clarity.",
    )

    # Get candidate outputs from previous step
    if candidates_step:
        candidate_output = await ctx.get(candidates_step)
        if candidate_output is None:
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=f"Candidate step '{candidates_step}' not found",
            )

        if candidate_output.status == StepStatus.FAILED:
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=f"Candidate step '{candidates_step}' failed: {candidate_output.error}",
            )

        # Extract candidate responses from metadata
        responses = candidate_output.metadata.get("responses", [])
        if not responses:
            # Fall back to single content
            if candidate_output.content:
                responses = [
                    {
                        "content": candidate_output.content,
                        "provider": candidate_output.provider,
                    }
                ]
            else:
                return StepOutput(
                    step_id=step.step_id,
                    status=StepStatus.FAILED,
                    error="No candidate responses to judge",
                )
    else:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No candidates_step specified for judge strategy",
        )

    # Build judge prompt
    candidates_text = ""
    for i, resp in enumerate(responses):
        content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
        provider = (
            resp.get("provider", "unknown") if isinstance(resp, dict) else "unknown"
        )
        candidates_text += (
            f"\n### Candidate {i + 1} (provider: {provider}):\n{content}\n"
        )

    judge_prompt = (
        f"You are a judge evaluating multiple AI responses.\n\n"
        f"Rubric: {rubric}\n\n"
        f"Here are the candidate responses:\n{candidates_text}\n\n"
        f"Evaluate each candidate and select the BEST one.\n"
        f"Output ONLY the number of the best candidate (e.g., '1' or '2').\n"
        f"Then on a new line, output the full content of the best response verbatim."
    )

    start = time.monotonic()

    try:
        router = ctx.globals.get("router")
        ctx.globals.get("request")

        # Use the router to get a judge response
        if router and hasattr(router, "route"):
            from freerelay.core.models.openai import (
                ChatCompletionRequest,
                Message,
            )

            judge_request = ChatCompletionRequest(
                model=step.params.get("judge_model", ""),
                messages=[
                    Message(role="user", content=judge_prompt),
                ],
                temperature=0.0,
                max_tokens=4096,
            )
            response = await router.route(judge_request)
            content = ""
            tokens = 0
            if response is not None and response.choices:
                content = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response is not None and response.usage else 0
        else:
            content = "1"  # Default to first candidate
            tokens = 0

        # Parse judge selection
        lines = content.strip().split("\n", 1)
        try:
            selection = int(lines[0].strip())
        except ValueError:
            selection = 1

        selected_idx = max(1, min(selection, len(responses)))
        selected_response = responses[selected_idx - 1]

        if isinstance(selected_response, dict):
            best_content = selected_response.get("content", "")
            best_provider = selected_response.get("provider", "")
        else:
            best_content = str(selected_response)
            best_provider = ""

        elapsed_ms = (time.monotonic() - start) * 1000

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=best_content,
            provider=best_provider,
            latency_ms=elapsed_ms,
            tokens_used=tokens,
            metadata={
                "judge_selection": selected_idx,
                "judge_reasoning": lines[1] if len(lines) > 1 else "",
                "num_candidates": len(responses),
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )
