"""
FreeRelay — Shared Internal Models (§3)
========================================
Canonical data models used across all FreeRelay components:
routing, execution, observability, tenancy, and agent orchestration.
"""

from __future__ import annotations

import enum
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

# ─── Enums (§3.1 — Workload Axes) ────────────────────────────────────────────


class TaskFamily(enum.StrEnum):
    """Top-level task classification."""

    CHAT = "chat"
    EXTRACTION = "extraction"
    CODING = "coding"
    PLANNING = "planning"
    TOOL_USE = "tool_use"
    RAG = "rag"
    EVAL = "eval"
    AGENT_LOOP = "agent_loop"


class Depth(enum.StrEnum):
    """Required reasoning depth."""

    SHALLOW = "shallow"
    MEDIUM = "medium"
    DEEP = "deep"


class Sensitivity(enum.StrEnum):
    """Precision / factual sensitivity."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LatencyClass(enum.StrEnum):
    """Latency requirement class."""

    INTERACTIVE = "interactive"
    ASYNC = "async_"
    BATCH = "batch"


class ContextTopology(enum.StrEnum):
    """Shape of the input context."""

    SHORT = "short"
    LONG = "long"
    FRAGMENTED = "fragmented"
    STRUCTURED = "structured"
    MULTIMODAL = "multimodal"


class ToolDependence(enum.StrEnum):
    """How much the task depends on tool calls."""

    NONE = "none"
    OPTIONAL = "optional"
    MANDATORY = "mandatory"


class Determinism(enum.StrEnum):
    """Required determinism of output."""

    LOW = "low"
    REPLAYABLE = "replayable"
    STRICT = "strict"


class SafetyPosture(enum.StrEnum):
    """Safety constraints for the request."""

    PERMISSIVE = "permissive"
    STANDARD = "standard"
    LOCKED_DOWN = "locked_down"


class OutputContract(enum.StrEnum):
    """Expected output format."""

    PROSE = "prose"
    JSON = "json"
    SCHEMA = "schema"
    CODE_PATCH = "code_patch"
    TOOL_CALLS = "tool_calls"


class EconomicPolicy(enum.StrEnum):
    """Cost optimization policy."""

    CHEAPEST = "cheapest"
    BALANCED = "balanced"
    BEST = "best"


# ─── WorkloadProfile (§3.1) ──────────────────────────────────────────────────


class WorkloadProfile(BaseModel):
    """
    Complete workload characterization produced by the profiler.
    Contains the 10 routing axes plus derived metrics and profiler metadata.
    """

    # Identity
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:16]}")
    namespace: str = "default"
    created_ts: float = Field(default_factory=time.time)

    # ── 10 Routing Axes ──────────────────────────────────────────────────────
    task_family: TaskFamily = TaskFamily.CHAT
    required_depth: Depth = Depth.MEDIUM
    precision_sensitivity: Sensitivity = Sensitivity.MEDIUM
    latency_class: LatencyClass = LatencyClass.ASYNC
    context_topology: ContextTopology = ContextTopology.SHORT
    tool_dependence: ToolDependence = ToolDependence.NONE
    determinism_needs: Determinism = Determinism.LOW
    safety_posture: SafetyPosture = SafetyPosture.STANDARD
    output_contract: OutputContract = OutputContract.PROSE
    economic_policy: EconomicPolicy = EconomicPolicy.BALANCED

    # ── Derived Metrics ──────────────────────────────────────────────────────
    prompt_tokens_estimated: int = 0
    context_tokens_estimated: int = 0
    tool_count: int = 0
    message_count: int = 0
    has_system_prompt: bool = False
    languages_detected: list[str] = Field(default_factory=list)
    has_images: bool = False
    json_schema_provided: bool = False

    # ── Profiler Metadata ────────────────────────────────────────────────────
    profiler_confidence: float = 1.0
    profiler_duration_ms: float = 0.0
    profiler_version: str = "1.0.0"


# ─── ProviderScore (§3.2) ────────────────────────────────────────────────────


class ProviderScore(BaseModel):
    """Score for a single provider/model candidate during routing."""

    provider: str = ""
    model: str = ""
    expected_utility: float = 0.0
    p_success: float = 0.0
    quality_estimate: float = 0.0
    schema_success_prob: float = 0.0
    latency_utility: float = 0.0
    cost_utility: float = 0.0
    safety_utility: float = 0.0
    circuit_score: float = 1.0
    budget_score: float = 1.0
    tenant_policy_score: float = 1.0
    ucb_bonus: float = 0.0
    disqualified: bool = False
    disqualification_reason: str = ""


# ─── RoutingDecision (§3.2) ──────────────────────────────────────────────────


class RoutingDecision(BaseModel):
    """Record of a routing decision with full scoring detail."""

    request_id: str = ""
    workload_profile: WorkloadProfile = Field(default_factory=WorkloadProfile)
    winner: ProviderScore = Field(default_factory=ProviderScore)
    all_candidates: list[ProviderScore] = Field(default_factory=list)
    confidence_gap: float = 0.0
    policy_version: str = ""
    workflow_selected: str = ""
    hedge_triggered: bool = False
    decision_duration_ms: float = 0.0


# ─── ValidationResult (§3.3) ─────────────────────────────────────────────────


class ValidationResult(BaseModel):
    """Result of a single validation layer."""

    layer: str = ""
    passed: bool = True
    score: float = 1.0
    failures: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0


# ─── OutcomeRecord (§3.3) ────────────────────────────────────────────────────


class OutcomeRecord(BaseModel):
    """
    Complete outcome record written after request completion.
    Feeds back into the routing learner and capability matrix.
    """

    # Identity
    request_id: str = ""
    namespace: str = "default"
    timestamp_utc: float = Field(default_factory=time.time)

    # Routing
    provider_chosen: str = ""
    model_chosen: str = ""
    all_candidates: list[ProviderScore] = Field(default_factory=list)
    confidence_gap: float = 0.0
    policy_version: str = ""
    workflow_used: str = ""

    # Workload
    workload_profile: WorkloadProfile = Field(default_factory=WorkloadProfile)

    # Execution
    latency_ttft_ms: float = 0.0
    latency_total_ms: float = 0.0
    tokens_prompt: int = 0
    tokens_completion: int = 0
    streaming: bool = False
    hedge_fired: bool = False
    hedge_winner: str = ""

    # Quality
    validation_results: list[ValidationResult] = Field(default_factory=list)
    output_valid: bool = True
    schema_passed: bool = True
    repair_triggered: bool = False
    repair_attempts: int = 0
    repair_success: bool = False
    judge_score: float = 0.0
    hallucination_flags: list[str] = Field(default_factory=list)

    # Context
    context_compression_ratio: float = 1.0
    cache_hit: bool = False
    cache_similarity_score: float = 0.0

    # Agent
    agent_run_id: str = ""
    agent_step_index: int = 0
    tool_calls_attempted: int = 0
    tool_calls_succeeded: int = 0

    # User behavior
    client_retried: bool = False
    client_regenerated: bool = False


# ─── AgentRunState (§13.1) ───────────────────────────────────────────────────


class AgentRunState(BaseModel):
    """State of a multi-step agent execution run."""

    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:16]}")
    namespace: str = "default"
    created_ts: float = Field(default_factory=time.time)
    status: str = "pending"  # pending | running | completed | failed | cancelled

    max_steps: int = 20
    max_budget_tokens: int = 100_000
    tokens_used: int = 0
    step_index: int = 0
    tool_permission_scope: list[str] = Field(default_factory=list)

    current_plan: str = ""
    completed_actions: list[dict[str, Any]] = Field(default_factory=list)
    tool_outputs: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_summaries: list[str] = Field(default_factory=list)
    rollback_points: list[dict[str, Any]] = Field(default_factory=list)

    routing_history: list[RoutingDecision] = Field(default_factory=list)
    tool_output_history: list[dict[str, Any]] = Field(default_factory=list)


# ─── AuditRecord (§14.2) ────────────────────────────────────────────────────


class AuditRecord(BaseModel):
    """Tamper-evident audit record with HMAC signature."""

    record_id: str = Field(default_factory=lambda: f"aud_{uuid.uuid4().hex[:16]}")
    timestamp_utc: float = Field(default_factory=time.time)
    namespace: str = "default"
    request_id: str = ""
    provider_called: str = ""
    prompt_hash: str = ""
    response_hash: str = ""
    pii_fields_masked: list[str] = Field(default_factory=list)
    routing_decision_hash: str = ""
    signature: str = ""


# ─── Auth & Billing ──────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str


class RegisterResponse(BaseModel):
    api_key: str

class TenantSettingsRequest(BaseModel):
    routing_preference: str # 'cost-optimized', 'balanced', 'performance-first'

class TenantSettingsResponse(BaseModel):
    success: bool
    routing_preference: str


class CheckoutRequest(BaseModel):
    email: str
    price_id: str


class CheckoutResponse(BaseModel):
    url: str


# ─── ConversationState (§8.3) ────────────────────────────────────────────────


class ConversationState(BaseModel):
    """State tracked across turns in a conversation session."""

    session_id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:16]}")
    goals: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    decisions_made: list[dict[str, Any]] = Field(default_factory=list)
    context_version: int = 0
    last_updated_ts: float = Field(default_factory=time.time)
