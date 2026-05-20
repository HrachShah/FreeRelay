"""
FreeRelay Data Plane — DAG Execution Engine (§8)
====================================================
Async Python runtime executing DAGs of inference steps.
Topological traversal with asyncio concurrency at frontier.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import yaml

from freerelay.data_plane.profiler.workload import WorkloadProfile

logger = logging.getLogger("freerelay.data_plane.dag")


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepKind(StrEnum):
    INFERENCE = "inference"
    JUDGE = "judge"
    REPAIR = "repair"
    VERIFY = "verify"
    MERGE = "merge"
    CONDITIONAL = "conditional"


@dataclass
class StepOutput:
    """Output from a single DAG step."""

    step_id: str
    status: StepStatus
    content: str = ""
    provider: str = ""
    model: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepDefinition:
    """Definition of a single step in the DAG."""

    step_id: str
    kind: StepKind
    strategy: str = "single"
    depends_on: list[str] = field(default_factory=list)
    condition: str | None = None  # Expression evaluated against context
    params: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 30000


@dataclass
class WorkflowDefinition:
    """A compiled workflow DAG."""

    name: str
    steps: list[StepDefinition] = field(default_factory=list)
    global_timeout_ms: int = 120000
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionTrace:
    """Record of a complete DAG execution."""

    trace_id: str
    workflow_name: str
    started_at: float
    completed_at: float = 0.0
    step_outputs: dict[str, StepOutput] = field(default_factory=dict)
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    status: str = "running"


# Strategy registry — populated by strategy imports
_STRATEGY_REGISTRY: dict[str, Callable[..., Coroutine[Any, Any, StepOutput]]] = {}


def register_strategy(name: str) -> Callable:
    """Decorator to register a strategy function."""

    def decorator(func: Callable[..., Coroutine[Any, Any, StepOutput]]) -> Callable:
        _STRATEGY_REGISTRY[name] = func
        return func

    return decorator


def get_strategy(name: str) -> Callable[..., Coroutine[Any, Any, StepOutput]] | None:
    """Look up a registered strategy by name."""
    return _STRATEGY_REGISTRY.get(name)


class ExecutionContext:
    """Shared execution context keyed by step_id."""

    def __init__(self) -> None:
        self._data: dict[str, StepOutput] = {}
        self._lock = asyncio.Lock()
        self.globals: dict[str, Any] = {}

    async def set(self, step_id: str, output: StepOutput) -> None:
        async with self._lock:
            self._data[step_id] = output

    async def get(self, step_id: str) -> StepOutput | None:
        async with self._lock:
            return self._data.get(step_id)

    async def get_all(self) -> dict[str, StepOutput]:
        async with self._lock:
            return dict(self._data)

    async def has(self, step_id: str) -> bool:
        async with self._lock:
            return step_id in self._data


def compile_workflow(yaml_str: str) -> WorkflowDefinition:
    """
    Compile a YAML workflow definition into a WorkflowDefinition DAG.

    YAML format:
      name: "my_workflow"
      global_timeout_ms: 120000
      steps:
        - step_id: "classify"
          kind: "inference"
          strategy: "single"
          depends_on: []
          timeout_ms: 30000
        - step_id: "generate"
          kind: "inference"
          strategy: "fanout"
          depends_on: ["classify"]
          params:
            n: 3
    """
    try:
        data = yaml.safe_load(yaml_str)
        if not data:
            return WorkflowDefinition(name="empty")

        steps: list[StepDefinition] = []
        for raw_step in data.get("steps", []):
            kind_str = raw_step.get("kind", "inference")
            try:
                kind = StepKind(kind_str)
            except ValueError:
                kind = StepKind.INFERENCE

            steps.append(
                StepDefinition(
                    step_id=raw_step["step_id"],
                    kind=kind,
                    strategy=raw_step.get("strategy", "single"),
                    depends_on=raw_step.get("depends_on", []),
                    condition=raw_step.get("condition"),
                    params=raw_step.get("params", {}),
                    timeout_ms=raw_step.get("timeout_ms", 30000),
                )
            )

        return WorkflowDefinition(
            name=data.get("name", "unnamed"),
            steps=steps,
            global_timeout_ms=data.get("global_timeout_ms", 120000),
            metadata=data.get("metadata", {}),
        )
    except Exception:
        logger.exception("Failed to compile workflow")
        return WorkflowDefinition(name="error")


def _topological_sort(steps: list[StepDefinition]) -> list[list[StepDefinition]]:
    """
    Topological sort into levels for concurrent execution.

    Returns:
        List of levels, where each level contains steps that can run in parallel.
    """
    step_map = {s.step_id: s for s in steps}
    in_degree = {s.step_id: len(s.depends_on) for s in steps}

    # Build adjacency: step → steps that depend on it
    dependents: dict[str, list[str]] = {s.step_id: [] for s in steps}
    for s in steps:
        for dep in s.depends_on:
            if dep in dependents:
                dependents[dep].append(s.step_id)

    levels: list[list[StepDefinition]] = []
    remaining = set(step_map.keys())

    while remaining:
        # Find all steps with in_degree == 0
        ready = [sid for sid in remaining if in_degree.get(sid, 0) == 0]
        if not ready:
            # Cycle detected — add remaining as final level
            logger.error("DAG cycle detected among steps: %s", remaining)
            levels.append([step_map[sid] for sid in remaining])
            break

        level = [step_map[sid] for sid in ready]
        levels.append(level)

        for sid in ready:
            remaining.discard(sid)
            for dependent in dependents.get(sid, []):
                in_degree[dependent] -= 1

    return levels


def _evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """
    Evaluate a simple condition expression against context.

    Supported: "step_id.status == 'completed'", "step_id.status != 'failed'",
               "step_id.content contains 'text'"
    """
    try:
        if "==" in condition:
            parts = condition.split("==", 1)
            field_path = parts[0].strip()
            expected = parts[1].strip().strip("'\"")
            actual = _resolve_path(field_path, context)
            return str(actual) == expected
        if "!=" in condition:
            parts = condition.split("!=", 1)
            field_path = parts[0].strip()
            expected = parts[1].strip().strip("'\"")
            actual = _resolve_path(field_path, context)
            return str(actual) != expected
        if " contains " in condition:
            parts = condition.split(" contains ", 1)
            field_path = parts[0].strip()
            expected = parts[1].strip().strip("'\"")
            actual = _resolve_path(field_path, context)
            return expected in str(actual) if actual else False
    except Exception:
        logger.debug("Condition evaluation failed: %s", condition)
    return True  # Default to true on parse failure


def _resolve_path(path: str, context: dict[str, Any]) -> Any:
    """Resolve dot-path in context dict."""
    parts = path.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, (list, tuple)) and part.isdigit():
            idx = int(part)
            current = current[idx] if 0 <= idx < len(current) else None
        elif part in current:
            current = current[part]
        else:
            return None
    return current


class DAGEngine:
    """
    DAG execution engine with async concurrency at the frontier.

    Executes workflow DAGs by:
      1. Topologically sorting steps into levels
      2. Running all steps in each level concurrently
      3. Propagating outputs to dependent steps
      4. Enforcing global timeout
      5. Recording execution trace
    """

    def __init__(self) -> None:
        self._strategies = _STRATEGY_REGISTRY

    async def execute(
        self,
        request: Any,
        workflow: WorkflowDefinition,
        router: Any | None = None,
        profile: WorkloadProfile | None = None,
    ) -> ExecutionTrace:
        """
        Execute a compiled workflow DAG.

        Args:
            request: The original request (ChatCompletionRequest).
            workflow: Compiled workflow definition.
            router: Router instance for strategy execution.
            profile: Optional workload profile.

        Returns:
            ExecutionTrace with all step outputs.
        """
        trace = ExecutionTrace(
            trace_id=f"trace_{uuid.uuid4().hex[:12]}",
            workflow_name=workflow.name,
            started_at=time.time(),
        )
        ctx = ExecutionContext()
        ctx.globals["request"] = request
        ctx.globals["router"] = router
        ctx.globals["profile"] = profile

        levels = _topological_sort(workflow.steps)

        try:
            async with asyncio.timeout(workflow.global_timeout_ms / 1000.0):
                for level in levels:
                    tasks = []
                    for step in level:
                        # Check condition
                        if step.condition:
                            cond_ctx = await self._build_condition_context(ctx)
                            if not _evaluate_condition(step.condition, cond_ctx):
                                skip_output = StepOutput(
                                    step_id=step.step_id,
                                    status=StepStatus.SKIPPED,
                                )
                                await ctx.set(step.step_id, skip_output)
                                trace.step_outputs[step.step_id] = skip_output
                                continue

                        tasks.append(self._execute_step(step, ctx, trace))

                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)

        except TimeoutError:
            logger.error(
                "Workflow %s timed out after %dms",
                workflow.name,
                workflow.global_timeout_ms,
            )
            trace.status = "timeout"
        except Exception as e:
            logger.exception("Workflow execution failed: %s", e)
            trace.status = "error"

        trace.completed_at = time.time()
        trace.total_latency_ms = (trace.completed_at - trace.started_at) * 1000

        all_outputs = await ctx.get_all()
        for output in all_outputs.values():
            trace.total_tokens += output.tokens_used
            if output.status == StepStatus.FAILED:
                trace.status = "failed"

        if trace.status == "running":
            trace.status = "completed"

        return trace

    async def _execute_step(
        self,
        step: StepDefinition,
        ctx: ExecutionContext,
        trace: ExecutionTrace,
    ) -> None:
        """Execute a single step with timeout."""
        start = time.monotonic()
        try:
            strategy_fn = self._strategies.get(step.strategy)
            if strategy_fn is None:
                output = StepOutput(
                    step_id=step.step_id,
                    status=StepStatus.FAILED,
                    error=f"Unknown strategy: {step.strategy}",
                )
            else:
                async with asyncio.timeout(step.timeout_ms / 1000.0):
                    output = await strategy_fn(step, ctx)

            output.latency_ms = (time.monotonic() - start) * 1000

        except TimeoutError:
            output = StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=f"Step timed out after {step.timeout_ms}ms",
                latency_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as e:
            output = StepOutput(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                error=str(e),
                latency_ms=(time.monotonic() - start) * 1000,
            )

        await ctx.set(step.step_id, output)
        trace.step_outputs[step.step_id] = output

    async def _build_condition_context(self, ctx: ExecutionContext) -> dict[str, Any]:
        """Build context dict for condition evaluation."""
        all_outputs = await ctx.get_all()
        result: dict[str, Any] = {}
        for step_id, output in all_outputs.items():
            result[step_id] = {
                "status": output.status.value,
                "content": output.content,
                "provider": output.provider,
                "model": output.model,
                "error": output.error,
            }
        return result
