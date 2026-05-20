"""
FreeRelay — Workload Profiler (§7)
====================================
Infer a structured workload profile from OpenAI requests for routing + context optimization.
Optimized with pre-compiled regex and frozenset keyword matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from freerelay.core.models.openai import ChatCompletionRequest

# Pre-compiled regex patterns for performance
_CODE_PATTERN = re.compile(r"\bcode\b")
_MULTILINGUAL_PATTERN = re.compile(
    r"[\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF\u0900-\u097F]"
)


@dataclass(slots=True)
class WorkloadProfile:
    """Structured workload profile emitted by the profiler."""

    task_family: str
    required_depth: str
    precision_sensitivity: str
    latency_class: str
    context_topology: str
    tool_dependence: str
    determinism_needs: str
    safety_posture: str
    output_contract: str
    economic_policy: str
    estimated_tokens: int
    message_count: int

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
        }


class WorkloadProfiler:
    """Heuristic workload profiler used before routing."""

    # Use frozensets for O(1) lookup and immutability
    _task_keywords: dict[str, frozenset[str]] = {
        "coding": frozenset(
            {
                "code",
                "function",
                "debug",
                "compile",
                "syntax",
                "json",
                "api",
                "script",
                "database",
            }
        ),
        "planning": frozenset(
            {"plan", "strategy", "roadmap", "sequence", "steps", "agenda"}
        ),
        "extraction": frozenset({"extract", "query", "parse", "summarize", "retrieve"}),
        "tool_use": frozenset({"tool", "function_call", "invoke", "tooling", "plugin"}),
        "RAG": frozenset({"source", "reference", "document", "retrieval", "cite"}),
        "eval": frozenset({"evaluate", "score", "judge", "testcase", "benchmark"}),
        "agent_loop": frozenset({"plan_and_execute", "chain", "loop", "step"}),
    }
    _precision_keywords = frozenset(
        {
            "exact",
            "precise",
            "strict",
            "validate",
            "certify",
            "legal",
            "medical",
            "correct",
        }
    )
    _deep_keywords = frozenset(
        {"analysis", "deep", "thorough", "thoughtful", "complex", "detailed"}
    )
    _safety_keywords = frozenset(
        {"legal", "medical", "finance", "security", "bury", "sensitive"}
    )
    _json_keywords = frozenset({"json", "schema", "format"})
    _code_keywords = frozenset({"code", "patch"})

    def profile(self, request: ChatCompletionRequest) -> WorkloadProfile:
        """Build a profile for a single chat completion request."""
        text = request.get_content_text().lower()
        # Split into word set once for efficient keyword matching
        words = set(text.split())
        tokens = request.estimate_tokens()
        message_count = len(request.messages)

        task_family = self._infer_task_family(text, words, request)
        required_depth = self._infer_depth(tokens, words)
        precision = self._infer_precision(task_family, words)
        latency = self._infer_latency_class(tokens, request)
        topology = self._infer_topology(tokens, text)
        tool_dependence = self._infer_tool_dependence(request)
        determinism = self._infer_determinism(request)
        safety = self._infer_safety(words)
        output_contract = self._infer_output_contract(request, words)
        economic = "balanced"

        return WorkloadProfile(
            task_family=task_family,
            required_depth=required_depth,
            precision_sensitivity=precision,
            latency_class=latency,
            context_topology=topology,
            tool_dependence=tool_dependence,
            determinism_needs=determinism,
            safety_posture=safety,
            output_contract=output_contract,
            economic_policy=economic,
            estimated_tokens=tokens,
            message_count=message_count,
        )

    def _infer_task_family(
        self,
        text: str,
        words: set[str],
        request: ChatCompletionRequest,
    ) -> str:
        if request.tools:
            return "tool_use"

        # Use set intersection for O(1) keyword matching
        for family, keywords in self._task_keywords.items():
            if words & keywords:
                return family

        if _CODE_PATTERN.search(text):
            return "coding"
        if _MULTILINGUAL_PATTERN.search(text):
            return "multilingual"
        return "chat"

    def _infer_depth(self, tokens: int, words: set[str]) -> str:
        if tokens > 6000 or words & self._deep_keywords:
            return "deep"
        if tokens > 1500:
            return "medium"
        return "shallow"

    def _infer_precision(self, task_family: str, words: set[str]) -> str:
        if task_family in {"coding", "eval"} or words & self._precision_keywords:
            return "high"
        if task_family in {"planning", "extraction"}:
            return "medium"
        return "low"

    def _infer_latency_class(self, tokens: int, request: ChatCompletionRequest) -> str:
        if request.is_streaming() or tokens < 1000:
            return "interactive"
        if tokens < 4000:
            return "async"
        return "batch"

    def _infer_topology(self, tokens: int, text: str) -> str:
        if "table" in text or "structured" in text:
            return "structured"
        if tokens > 5000:
            return "long"
        if "..." in text or "|" in text:
            return "fragmented"
        return "short"

    def _infer_tool_dependence(self, request: ChatCompletionRequest) -> str:
        if request.tools:
            return "mandatory"
        if any(msg.role == "tool" or msg.tool_calls for msg in request.messages):
            return "optional"
        return "none"

    def _infer_determinism(self, request: ChatCompletionRequest) -> str:
        temperature = request.temperature if request.temperature is not None else 0.7
        if request.seed is not None or temperature <= 0.2:
            return "strict"
        if temperature <= 0.5:
            return "replayable"
        return "low"

    def _infer_safety(self, words: set[str]) -> str:
        if words & self._safety_keywords:
            return "locked_down"
        return "standard"

    def _infer_output_contract(
        self, request: ChatCompletionRequest, words: set[str]
    ) -> str:
        if request.response_format and request.response_format.type == "json_object":
            return "schema"
        if request.response_format and request.response_format.type == "text":
            return "prose"
        if words & self._json_keywords:
            return "json"
        if words & self._code_keywords:
            return "code_patch"
        return "prose"
