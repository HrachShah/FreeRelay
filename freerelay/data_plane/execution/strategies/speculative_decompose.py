"""
FreeRelay Data Plane — Speculative Decompose Strategy
=======================================================
Heuristic decomposition, parallel execution, synthesis.
"""

from __future__ import annotations

import asyncio
import re
import time

from freerelay.data_plane.execution.dag_engine import (
    ExecutionContext,
    StepDefinition,
    StepOutput,
    StepStatus,
    register_strategy,
)


@register_strategy("speculative_decompose")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Heuristic decomposition without LLM planning.

    Uses regex/keyword heuristics to split complex requests into subtasks,
    executes them in parallel, then synthesizes results.
    """
    request = ctx.globals.get("request")
    router = ctx.globals.get("router")

    if request is None:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error="No request in execution context",
        )

    start = time.monotonic()
    text = request.get_content_text()

    try:
        # Heuristic decomposition
        subtasks = _decompose_heuristic(text)

        if len(subtasks) <= 1:
            # No decomposition possible, execute directly
            if router and hasattr(router, "route"):
                response = await router.route(request)
                content = ""
                tokens = 0
                if response is not None and response.choices:
                    content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response is not None and response.usage else 0
            else:
                content = ""
                tokens = 0

            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                content=content,
                latency_ms=(time.monotonic() - start) * 1000,
                tokens_used=tokens,
                metadata={"decomposed": False, "num_subtasks": 1},
            )

        # Execute subtasks in parallel
        async def exec_subtask(subtask: str) -> str:
            if router and hasattr(router, "route"):
                from freerelay.core.models.openai import (
                    ChatCompletionRequest,
                    Message,
                )

                req = ChatCompletionRequest(
                    model=step.params.get("model", ""),
                    messages=[
                        Message(
                            role="user",
                            content=f"{subtask}\n\nContext from original request:\n{text[:1000]}",
                        ),
                    ],
                    temperature=0.3,
                    max_tokens=1024,
                )
                response = await router.route(req)
                if response is not None and response.choices:
                    return response.choices[0].message.content or ""
            return ""

        tasks = [exec_subtask(st) for st in subtasks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        successful = [r for r in results if isinstance(r, str) and r]

        if not successful:
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error="All subtask executions failed",
            )

        # Synthesize
        if len(successful) == 1:
            final = successful[0]
        else:
            parts = [f"Part {i + 1}: {r}" for i, r in enumerate(successful)]
            final = "\n\n".join(parts)

        elapsed_ms = (time.monotonic() - start) * 1000

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=final,
            latency_ms=elapsed_ms,
            metadata={
                "decomposed": True,
                "num_subtasks": len(subtasks),
                "succeeded": len(successful),
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )


def _decompose_heuristic(text: str) -> list[str]:
    """
    Heuristic decomposition using regex patterns.

    Looks for numbered lists, bullet points, "step" patterns,
    or multiple distinct questions.
    """
    # Pattern 1: Numbered list items
    numbered = re.findall(
        r"(?:^|\n)\s*\d+[\.\)]\s*(.+?)(?=\n\s*\d+[\.\)]|\Z)", text, re.DOTALL
    )
    if len(numbered) >= 2:
        return [item.strip() for item in numbered if item.strip()]

    # Pattern 2: Bullet points
    bullets = re.findall(r"(?:^|\n)\s*[-*•]\s*(.+?)(?=\n\s*[-*•]|\Z)", text, re.DOTALL)
    if len(bullets) >= 2:
        return [item.strip() for item in bullets if item.strip()]

    # Pattern 3: Multiple questions
    questions = re.findall(r"([^.?!]*\?)", text)
    if len(questions) >= 2:
        return [q.strip() for q in questions if len(q.strip()) > 10]

    # Pattern 4: "First... Second... Third..." patterns
    ordinal_pattern = re.findall(
        r"(?:First|Second|Third|Fourth|Fifth|Finally)[,:]?\s*(.+?)(?=(?:First|Second|Third|Fourth|Fifth|Finally)[,:]|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if len(ordinal_pattern) >= 2:
        return [item.strip() for item in ordinal_pattern if item.strip()]

    # No decomposition possible
    return [text]
