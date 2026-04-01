"""
FreeRelay Settings — Pydantic BaseSettings
============================================
All configuration from env vars / .env file, fully typed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderKeys(BaseSettings):
    """API keys for all supported providers."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    google_ai_key: str = ""
    openrouter_api_key: str = ""
    together_api_key: str = ""
    mistral_api_key: str = ""
    nvidia_api_key: str = ""

    # Paid/premium API keys (optional)
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # OpenCode platform keys (optional)
    opencode_api_key: str = ""  # OPENCODE_API_KEY or OPENCODE_ZEN_API_KEY


class Settings(BaseSettings):
    """Master settings for FreeRelay."""

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="FREERELAY_", extra="ignore"
    )

    # ── Mode ─────────────────────────────────────────────────
    mode: str = "auto"  # "free", "paid", "auto" (auto = use free if available, paid if no free keys)

    # ── Server ────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Gateway Auth ──────────────────────────────────────
    api_key: str = ""  # If set, clients must send this as Bearer token
    enable_auth: bool = False

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"
    enable_redis: bool = False  # Start without Redis by default

    # ── Timeouts ──────────────────────────────────────────
    request_timeout: int = 60  # seconds

    # ── Circuit Breaker ───────────────────────────────────
    circuit_failure_threshold: int = 5
    circuit_failure_window: int = 60  # seconds
    circuit_recovery_timeout: int = 30  # seconds

    # ── Budget ────────────────────────────────────────────
    budget_safety_margin_tokens: int = 10_000
    budget_ewma_alpha: float = 0.3

    # ── Cache ─────────────────────────────────────────────
    enable_cache: bool = False
    cache_similarity_threshold: float = 0.92
    cache_ttl: int = 3600  # seconds
    cache_minhash_perms: int = 128

    # ── Compression ───────────────────────────────────────
    enable_compression: bool = True
    compression_summarize_threshold: int = 8000  # tokens
    compression_min_ratio: float = 0.5

    # ── Rate Limiting ────────────────────────────────────
    rate_limit_rpm: int = 60
    rate_limit_burst: int = 10

    # ── Idempotency ──────────────────────────────────────
    idempotency_ttl: int = 600  # seconds

    # ── Routing ───────────────────────────────────────────
    enable_hedging: bool = False
    max_repair_attempts: int = 2

    # ── Streaming ─────────────────────────────────────────
    stream_buffer_size: int = 32  # max chunks in backpressure queue

    # ── Chaos ─────────────────────────────────────────────
    enable_chaos: bool = False
    chaos_intensity: float = 0.1  # 0.0-1.0

    # ── Observability ─────────────────────────────────────
    enable_telemetry: bool = False
    enable_prometheus: bool = False
    otel_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    # ── Paths ─────────────────────────────────────────────
    plugin_dir: Path = Path.home() / ".freerelay" / "plugins"
    capability_matrix_path: str = ""
    routing_rules_path: str = ""

    # ── Provider keys (nested) ────────────────────────────
    keys: ProviderKeys = Field(default_factory=ProviderKeys)


@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()
