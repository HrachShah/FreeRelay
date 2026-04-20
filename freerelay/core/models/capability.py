"""
FreeRelay — Capability Matrix Models
=======================================
Pydantic models for the capability_matrix.yaml schema.
Used by the routing engine to match requests to providers.
"""

from __future__ import annotations

from pydantic import BaseModel


class FreeTierLimits(BaseModel):
    """Free tier rate limits for a model."""
    rpm: int | None = None  # requests per minute
    tpm: int | None = None  # tokens per minute
    tpd: int | None = None  # tokens per day


class ModelCapability(BaseModel):
    """Capability profile for a single model."""
    provider: str
    context_window: int = 8192
    strengths: list[str] = []
    weaknesses: list[str] = []
    speed_tier: str = "medium"  # fast | medium | slow
    quality_tier: str = "medium"  # low | medium | high
    free_tier: FreeTierLimits = FreeTierLimits()
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    supports_logprobs: bool = False
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0


class CapabilityMatrix(BaseModel):
    """Full capability database."""
    models: dict[str, ModelCapability] = {}

    def get_model(self, model_id: str) -> ModelCapability | None:
        """Look up a model by its full ID (e.g. 'groq/llama-3.1-70b-versatile')."""
        return self.models.get(model_id)

    def get_provider_models(self, provider: str) -> dict[str, ModelCapability]:
        """Get all models for a specific provider."""
        return {
            k: v for k, v in self.models.items()
            if v.provider == provider
        }

    def get_models_with_strength(self, strength: str) -> dict[str, ModelCapability]:
        """Find models that have a specific strength."""
        return {
            k: v for k, v in self.models.items()
            if strength in v.strengths
        }
