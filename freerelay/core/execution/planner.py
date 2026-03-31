"""
FreeRelay — Execution Graph Planner (§11)
==================================================
Builds declarative execution DAGs from workload profiles and routing directives.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from freerelay.core.intelligence.profiler import WorkloadProfile
from freerelay.core.routing.policy import RoutingDirective


@dataclass
class ExecutionStep:
    """Single step within an execution workflow."""

    name: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class ExecutionGraph:
    """Simple linear representation of an execution DAG."""

    steps: list[ExecutionStep] = field(default_factory=list)


class ExecutionPlanner:
    """Converts workload profile + policy directive into execution steps."""

    def plan(
        self,
        profile: WorkloadProfile,
        directive: RoutingDirective | None,
    ) -> ExecutionGraph:
        steps: list[ExecutionStep] = []

        steps.append(
            ExecutionStep(
                name="classify_workload",
                details={
                    "task_family": profile.task_family,
                    "latency_class": profile.latency_class,
                },
            )
        )

        fanout = directive.fanout if directive and directive.fanout else 1
        steps.append(
            ExecutionStep(
                name="generate",
                details={
                    "fanout": fanout,
                    "preferred_models": directive.prefer if directive else [],
                },
            )
        )

        if directive and directive.validators:
            steps.append(
                ExecutionStep(
                    name="validate",
                    details={
                        "validators": directive.validators,
                        "enforce_mode": directive.enforce_mode,
                    },
                )
            )

        if directive and directive.require_hedging:
            steps.append(
                ExecutionStep(
                    name="hedging",
                    details={
                        "strategy": directive.require_hedging,
                    },
                )
            )

        if directive and directive.human_gate:
            steps.append(ExecutionStep(name="human_gate"))

        steps.append(
            ExecutionStep(
                name="select",
                details={
                    "policy_weight": directive.policy_weight if directive else 1.0,
                },
            )
        )

        return ExecutionGraph(steps=steps)
