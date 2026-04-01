"""
FreeRelay Data Plane — Planner-Executor Strategy
===================================================
Planner decomposes request into subtasks, executors run subtasks, planner merges.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from freerelay.data_plane.execution.dag_engine import (
    ExecutionContext,
    StepDefinition,
    StepOutput,
    StepStatus,
    register_strategy,
)


@register_strategy("planner_executor")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Two-phase execution: plan then execute.

    Phase 1: Planner decomposes the request into subtasks.
    Phase 2: Executors run each subtask in parallel.
    Phase 3: Planner merges results into final answer.
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
    original_text = request.get_content_text()

    try:
        # Phase 1: Plan
        plan_prompt = (
            f"You are a task planner. Decompose the following request into subtasks.\n\n"
            f"Request:\n{original_text}\n\n"
            f"Output a JSON array of subtasks:\n"
            f'[{{"id": 1, "description": "...", "expected_output": "..."}}, ...]\n'
            f"Output ONLY the JSON array."
        )

        plan_content = await _call_llm(router, step, plan_prompt)

        try:
            subtasks = json.loads(plan_content)
            if not isinstance(subtasks, list):
                subtasks = [
                    {
                        "id": 1,
                        "description": original_text,
                        "expected_output": "Full response",
                    }
                ]
        except json.JSONDecodeError:
            subtasks = [
                {
                    "id": 1,
                    "description": original_text,
                    "expected_output": "Full response",
                }
            ]

        # Phase 2: Execute subtasks in parallel
        async def execute_subtask(subtask: dict[str, Any]) -> tuple[int, str]:
            exec_prompt = (
                f"Complete this specific subtask:\n\n"
                f"Subtask: {subtask.get('description', '')}\n"
                f"Expected output: {subtask.get('expected_output', '')}\n\n"
                f"Original context:\n{original_text[:2000]}\n\n"
                f"Provide the complete answer for this subtask."
            )
            content = await _call_llm(router, step, exec_prompt)
            return (subtask.get("id", 0), content)

        exec_tasks = [execute_subtask(st) for st in subtasks]
        exec_results = await asyncio.gather(*exec_tasks, return_exceptions=True)

        # Collect successful results
        subtask_outputs: dict[int, str] = {}
        for result in exec_results:
            if isinstance(result, tuple):
                subtask_outputs[result[0]] = result[1]

        # Phase 3: Merge
        merge_parts = []
        for st in subtasks:
            sid = st.get("id", 0)
            if sid in subtask_outputs:
                merge_parts.append(
                    f"Subtask {sid} ({st.get('description', '')}):\n{subtask_outputs[sid]}"
                )

        if len(merge_parts) == 1:
            final_content = merge_parts[0]
        else:
            merge_prompt = (
                "Combine these subtask results into a coherent final response:\n\n"
                + "\n\n".join(merge_parts)
                + f"\n\nOriginal request:\n{original_text}\n\n"
                f"Provide the unified final answer."
            )
            final_content = await _call_llm(router, step, merge_prompt)

        elapsed_ms = (time.monotonic() - start) * 1000

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=final_content,
            latency_ms=elapsed_ms,
            metadata={
                "num_subtasks": len(subtasks),
                "subtasks_succeeded": len(subtask_outputs),
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )


async def _call_llm(router: Any, step: StepDefinition, prompt: str) -> str:
    """Call the LLM via router for planning/execution/merge."""
    if router and hasattr(router, "route"):
        from freerelay.core.models.openai import (
            ChatCompletionRequest,
            Message,
        )

        req = ChatCompletionRequest(
            model=step.params.get("model", ""),
            messages=[Message(role="user", content=prompt)],
            temperature=step.params.get("temperature", 0.3),
            max_tokens=step.params.get("max_tokens", 2048),
        )
        response = await router.route(req)
        if response.choices:
            return response.choices[0].message.content or ""
    return ""
