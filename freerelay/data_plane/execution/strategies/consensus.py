"""
FreeRelay Data Plane — Consensus Strategy
============================================
N providers, pairwise similarity, if agreement >= threshold return, else judge.
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


@register_strategy("consensus")
async def execute(
    step: StepDefinition,
    ctx: ExecutionContext,
) -> StepOutput:
    """
    Run N providers, check pairwise similarity for consensus.

    Params:
        n: Number of providers (default: 3)
        agreement_threshold: Minimum pairwise similarity (default: 0.8)
        model_pool: List of ModelSlot dicts
    """
    request = ctx.globals.get("request")
    router = ctx.globals.get("router")
    profile = ctx.globals.get("profile")
    n = step.params.get("n", 3)
    agreement_threshold = step.params.get("agreement_threshold", 0.8)

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
            top_n = router.select_top_n(profile, model_pool, n=n)
        else:
            top_n = [(step.params.get("provider", ""), step.params.get("model", ""))]

        # Fan out
        async def call_provider(provider: str, model: str) -> tuple[str, str, int]:
            if hasattr(router, "route"):
                response = await router.route(request)
                content = ""
                tokens = 0
                if response is not None:
                    if response.choices:
                        content = response.choices[0].message.content or ""
                    tokens = response.usage.total_tokens if response.usage else 0
                else:
                    content = ""
                    tokens = 0
                return (content, provider, tokens)
            return ("", provider, 0)

        tasks = [call_provider(p, m) for p, m in top_n]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = [r for r in results if isinstance(r, tuple) and r[0]]

        if not successful:
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error="All providers failed",
            )

        # Need at least 2 responses to establish consensus — a single provider
        # has no one to agree with, so skip straight to judge.
        if len(successful) < 2:
            from freerelay.data_plane.execution.strategies.judge import (
                execute as judge_execute,
            )

            candidate_step_id = f"{step.step_id}_candidates"
            await ctx.set(
                candidate_step_id,
                StepOutput(
                    step_id=candidate_step_id,
                    status=StepStatus.COMPLETED,
                    metadata={
                        "responses": [
                            {"content": r[0], "provider": r[1]} for r in successful
                        ],
                    },
                ),
            )

            judge_step = StepDefinition(
                step_id=f"{step.step_id}_judge",
                kind=step.kind,
                strategy="judge",
                params={
                    "candidates_step": candidate_step_id,
                    "rubric": step.params.get(
                        "rubric", "Select the most accurate and complete response."
                    ),
                },
            )

            judge_output = await judge_execute(judge_step, ctx)
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                content=judge_output.content,
                provider=judge_output.provider,
                model=judge_output.model,
                latency_ms=(time.monotonic() - start) * 1000,
                tokens_used=judge_output.tokens_used,
                metadata={
                    "consensus": False,
                    "similarity": 1.0,
                    "n_responded": len(successful),
                    "judge_used": True,
                    "single_provider": True,
                },
            )

        # Check pairwise similarity
        contents = [r[0] for r in successful]
        similarity = _pairwise_similarity(contents) if len(contents) >= 2 else 1.0

        total_tokens = sum(r[2] for r in successful)

        if similarity >= agreement_threshold:
            # Consensus reached — return the first (best scored) response
            return StepOutput(
                step_id=step.step_id,
                status=StepStatus.COMPLETED,
                content=successful[0][0],
                provider=successful[0][1],
                latency_ms=(time.monotonic() - start) * 1000,
                tokens_used=total_tokens,
                metadata={
                    "consensus": True,
                    "similarity": similarity,
                    "n_responded": len(successful),
                },
            )

        # No consensus — fall through to judge
        from freerelay.data_plane.execution.strategies.judge import (
            execute as judge_execute,
        )

        # Store candidates in context for judge
        candidate_step_id = f"{step.step_id}_candidates"
        await ctx.set(
            candidate_step_id,
            StepOutput(
                step_id=candidate_step_id,
                status=StepStatus.COMPLETED,
                metadata={
                    "responses": [
                        {"content": r[0], "provider": r[1]} for r in successful
                    ],
                },
            ),
        )

        judge_step = StepDefinition(
            step_id=f"{step.step_id}_judge",
            kind=step.kind,
            strategy="judge",
            params={
                "candidates_step": candidate_step_id,
                "rubric": step.params.get(
                    "rubric", "Select the most accurate and complete response."
                ),
            },
        )

        judge_output = await judge_execute(judge_step, ctx)

        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.COMPLETED,
            content=judge_output.content,
            provider=judge_output.provider,
            model=judge_output.model,
            latency_ms=(time.monotonic() - start) * 1000,
            tokens_used=total_tokens + judge_output.tokens_used,
            metadata={
                "consensus": False,
                "similarity": similarity,
                "n_responded": len(successful),
                "judge_used": True,
            },
        )

    except Exception as e:
        return StepOutput(
            step_id=step.step_id,
            status=StepStatus.FAILED,
            error=str(e),
            latency_ms=(time.monotonic() - start) * 1000,
        )


def _pairwise_similarity(contents: list[str]) -> float:
    """
    Compute average pairwise similarity using character n-gram Jaccard.
    """
    if len(contents) < 2:
        return 1.0

    def _ngrams(text: str, n: int = 3) -> set[str]:
        text = text.lower()
        return {text[i : i + n] for i in range(len(text) - n + 1)}

    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 1.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    ngrams_list = [_ngrams(c) for c in contents]
    total_sim = 0.0
    pairs = 0

    for i in range(len(ngrams_list)):
        for j in range(i + 1, len(ngrams_list)):
            total_sim += _jaccard(ngrams_list[i], ngrams_list[j])
            pairs += 1

    return total_sim / pairs if pairs > 0 else 1.0
