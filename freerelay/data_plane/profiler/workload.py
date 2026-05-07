"""
FreeRelay Data Plane — Workload Profiler (§4)
================================================
10-axis workload classification in <5ms p99.
Pure local computation — no LLM calls, no network calls.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from freerelay.core.models.openai import ChatCompletionRequest

logger = logging.getLogger("freerelay.data_plane.profiler")


@dataclass
class WorkloadProfile:
    """Structured workload profile with all 10 classification axes."""

    task_family: str = "chat"
    required_depth: str = "medium"
    precision_sensitivity: str = "low"
    latency_class: str = "async"
    context_topology: str = "short"
    tool_dependence: str = "none"
    determinism_needs: str = "low"
    safety_posture: str = "standard"
    output_contract: str = "prose"
    economic_policy: str = "balanced"
    estimated_tokens: int = 0
    message_count: int = 0
    confidence: float = 0.0

    # Per-axis confidence scores
    axis_confidences: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Flatten profile for policy evaluation."""
        return {
            "task_family": self.task_family,
            "required_depth": self.required_depth,
            "precision_sensitivity": self.precision_sensitivity,
            "latency_class": self.latency_class,
            "context_topology": self.context_topology,
            "tool_dependence": self.tool_dependence,
            "determinism_needs": self.determinism_needs,
            "safety_posture": self.safety_posture,
            "output_contract": self.output_contract,
            "economic_policy": self.economic_policy,
            "estimated_tokens": self.estimated_tokens,
            "message_count": self.message_count,
            "confidence": self.confidence,
        }


class WorkloadProfiler:
    """
    Orchestrates all 10 axis classifiers to produce a WorkloadProfile.

    Must complete in <5ms p99 (spec §4.1):
      - No LLM calls
      - No network calls
      - Pure local computation with keyword heuristics and rule tables
    """

    def __init__(self) -> None:
        from freerelay.data_plane.profiler.axes.context_topology import (
            classify_context_topology,
        )
        from freerelay.data_plane.profiler.axes.determinism_needs import (
            classify_determinism_needs,
        )
        from freerelay.data_plane.profiler.axes.economic_policy import (
            classify_economic_policy,
        )
        from freerelay.data_plane.profiler.axes.latency_class import (
            classify_latency_class,
        )
        from freerelay.data_plane.profiler.axes.output_contract import (
            classify_output_contract,
        )
        from freerelay.data_plane.profiler.axes.precision_sensitivity import (
            classify_precision_sensitivity,
        )
        from freerelay.data_plane.profiler.axes.required_depth import (
            classify_required_depth,
        )
        from freerelay.data_plane.profiler.axes.safety_posture import (
            classify_safety_posture,
        )
        from freerelay.data_plane.profiler.axes.task_family import classify_task_family
        from freerelay.data_plane.profiler.axes.tool_dependence import (
            classify_tool_dependence,
        )

        self._classifiers = {
            "task_family": classify_task_family,
            "required_depth": classify_required_depth,
            "precision_sensitivity": classify_precision_sensitivity,
            "latency_class": classify_latency_class,
            "context_topology": classify_context_topology,
            "tool_dependence": classify_tool_dependence,
            "determinism_needs": classify_determinism_needs,
            "safety_posture": classify_safety_posture,
            "output_contract": classify_output_contract,
            "economic_policy": classify_economic_policy,
        }

    def profile(
        self,
        request: ChatCompletionRequest,
        headers: dict[str, str] | None = None,
    ) -> WorkloadProfile:
        """
        Profile a request across all 10 axes.

        Args:
            request: The OpenAI-format chat completion request.
            headers: Optional HTTP headers for header-based classifiers.

        Returns:
            WorkloadProfile with all axes classified and confidence computed.
        """
        start = time.monotonic()
        headers = headers or {}
        axis_confidences: dict[str, float] = {}
        values: dict[str, str] = {}

        for axis_name, classifier in self._classifiers.items():
            try:
                value, confidence = classifier(request, headers)
                values[axis_name] = value
                axis_confidences[axis_name] = confidence
            except (TypeError, KeyError, ValueError, AttributeError):
                logger.exception("Axis classifier %s failed", axis_name)
                values[axis_name] = "unknown"
                axis_confidences[axis_name] = 0.0

        profile = WorkloadProfile(
            task_family=values.get("task_family", "chat"),
            required_depth=values.get("required_depth", "medium"),
            precision_sensitivity=values.get("precision_sensitivity", "low"),
            latency_class=values.get("latency_class", "async"),
            context_topology=values.get("context_topology", "short"),
            tool_dependence=values.get("tool_dependence", "none"),
            determinism_needs=values.get("determinism_needs", "low"),
            safety_posture=values.get("safety_posture", "standard"),
            output_contract=values.get("output_contract", "prose"),
            economic_policy=values.get("economic_policy", "balanced"),
            estimated_tokens=request.estimate_tokens(),
            message_count=len(request.messages),
            axis_confidences=axis_confidences,
            confidence=self._compute_confidence(axis_confidences),
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        if elapsed_ms > 5.0:
            logger.warning("Workload profiling took %.2fms (>5ms target)", elapsed_ms)

        return profile

    @staticmethod
    def _compute_confidence(axis_confidences: dict[str, float]) -> float:
        """
        Compute overall confidence per spec §4.2.

        confidence = geometric_mean(per_axis_confidence)
        Falls back to arithmetic mean if any confidence is 0.
        """
        if not axis_confidences:
            return 0.0

        values = list(axis_confidences.values())
        if any(v <= 0 for v in values):
            # Geometric mean undefined with zeros; use arithmetic mean
            return sum(values) / len(values)

        product = 1.0
        for v in values:
            product *= v
        return product ** (1.0 / len(values))
