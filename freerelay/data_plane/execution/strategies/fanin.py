"""
FreeRelay Data Plane — Fanin Strategy
========================================
Collect outputs from multiple upstream steps, merge into single prompt.
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


@register_strategy("fanin")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Collect outputs from multiple upstream steps and merge them.

    Params:
        source_steps: List of step IDs to collect from
        merge_strategy: How to merge (concatenate, summarize, select_best)
        separator: Separator for concatenation (default: "\n\n---\n\n")
    """
    source_steps = step.params.get("source_steps", [])
    merge_strategy = step.params.get("merge_strategy", "concatenate")
    separator = step.params.get("separator", "\n\n---\n\n")

    if not source_steps:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No source_steps specified for fanin",
        )

    start = time.monotonic()

    try:
        # Collect all source outputs
        collected: list[StepOutput] = []
        for sid in source_steps:
            output = await ctx.get(sid)
            if output is not None and output.status == StepStatus.COMPLETED:
                collected.append(output)

        if not collected:
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=f"No completed outputs from source steps: {source_steps}",
            )

        # Merge based on strategy
        if merge_strategy == "concatenate":
            merged_content = separator.join(r.content for r in collected if r.content)
            total_tokens = sum(r.tokens_used for r in collected)

        elif merge_strategy == "select_best":
            # Select the longest response as "best"
            best = max(collected, key=lambda r: len(r.content))
            merged_content = best.content
            total_tokens = sum(r.tokens_used for r in collected)

        elif merge_strategy == "summarize":
            # Use LLM to summarize combined outputs
            combined = separator.join(
                f"[From {r.provider}/{r.model}]:\n{r.content}"
                for r in collected
                if r.content
            )

            router = ctx.globals.get("router")
            if router and hasattr(router, "route"):
                from freerelay.core.models.openai import (
                    ChatCompletionRequest,
                    Message,
                )

                summarize_request = ChatCompletionRequest(
                    model=step.params.get("model", ""),
                    messages=[
                        Message(
                            role="user",
                            content=(
                                f"Summarize the following combined outputs into a coherent response:\n\n{combined}"
                            ),
                        ),
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                )
                response = await router.route(summarize_request)
                merged_content = ""
                total_tokens = 0
                if response is not None:
                    if response.choices:
                        merged_content = response.choices[0].message.content or ""
                    total_tokens = response.usage.total_tokens if response.usage else 0
            else:
                merged_content = combined
                total_tokens = sum(r.tokens_used for r in collected)

        else:
            merged_content = separator.join(r.content for r in collected if r.content)
            total_tokens = sum(r.tokens_used for r in collected)

        elapsed_ms = (time.monotonic() - start) * 1000

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=merged_content,
            provider=collected[0].provider if collected else "",
            model=collected[0].model if collected else "",
            latency_ms=elapsed_ms,
            tokens_used=total_tokens,
            metadata={
                "merge_strategy": merge_strategy,
                "num_sources": len(source_steps),
                "num_collected": len(collected),
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )
