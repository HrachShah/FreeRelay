from __future__ import annotations

from datetime import datetime
from freerelay._compat import StrEnum

from pydantic import BaseModel, Field


class TaskFamily(StrEnum):
    CHAT = "chat"
    CODING = "coding"
    REASONING = "reasoning"
    INSTRUCTION_FOLLOWING = "instruction_following"
    SUMMARIZATION = "summarization"
    EXTRACTION = "extraction"
    TRANSLATION = "translation"
    CREATIVE = "creative"


class OutputContract(StrEnum):
    PROSE = "prose"
    JSON = "json"
    CODE = "code"
    TOOL_CALLS = "tool_calls"
    MARKDOWN = "markdown"


class LatencyMetrics(BaseModel):
    p50_ms: float
    p95_ms: float
    p99_ms: float
    sample_count: int


class SchemaCompliance(BaseModel):
    output_contract: OutputContract
    compliance_rate: float
    total_attempts: int
    successful: int


class QuotaState(BaseModel):
    provider: str
    model: str
    quota_remaining: int
    quota_total: int
    hourly_updated: datetime


class BenchmarkHistory(BaseModel):
    provider: str
    model: str
    suite: str
    scores: list[tuple[datetime, float]] = Field(default_factory=list)
    history_days: int = 30


class AnomalyAlert(BaseModel):
    provider: str
    model: str
    anomaly_type: str
    detected_at: datetime
    details: str | None = None


class ProviderMetrics(BaseModel):
    provider: str
    model: str
    task_family: TaskFamily
    avg_latency_ms: float
    success_rate: float
    quality_score: float
    schema_compliance: dict[OutputContract, float]
    long_context_recall: float | None = None
    last_updated: datetime


class LeaderboardEntry(BaseModel):
    rank: int
    provider: str
    model: str
    task_family: TaskFamily
    quality_score: float
    latency_p50_ms: float
    latency_p95_ms: float
    schema_compliance_rate: float
    confidence: float


class TaskFamilyRanking(BaseModel):
    task_family: TaskFamily
    entries: list[LeaderboardEntry]
    updated_at: datetime


class LeaderboardResponse(BaseModel):
    rankings: dict[TaskFamily, TaskFamilyRanking]
    latency_metrics: dict[str, dict[str, LatencyMetrics]]
    schema_compliance: list[SchemaCompliance]
    quota_states: list[QuotaState]
    benchmark_history: list[BenchmarkHistory]
    anomaly_alerts: list[AnomalyAlert]
    generated_at: datetime
