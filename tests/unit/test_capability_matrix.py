"""
Tests — Capability Matrix
============================
Verify capability matrix loading and model lookup.
"""

from freerelay.core.models.capability import (
    CapabilityMatrix,
    FreeTierLimits,
    ModelCapability,
)


class TestFreeTierLimits:
    def test_defaults(self) -> None:
        limits = FreeTierLimits()
        assert limits.rpm is None
        assert limits.tpm is None
        assert limits.tpd is None

    def test_with_values(self) -> None:
        limits = FreeTierLimits(rpm=30, tpm=6000, tpd=500000)
        assert limits.rpm == 30
        assert limits.tpm == 6000
        assert limits.tpd == 500000


class TestModelCapability:
    def test_defaults(self) -> None:
        cap = ModelCapability(provider="groq")
        assert cap.context_window == 8192
        assert cap.strengths == []
        assert cap.weaknesses == []
        assert cap.speed_tier == "medium"
        assert cap.quality_tier == "medium"
        assert cap.supports_streaming is True
        assert cap.supports_tools is False

    def test_with_strengths(self) -> None:
        cap = ModelCapability(
            provider="groq",
            strengths=["coding", "reasoning"],
            weaknesses=["multilingual"],
            speed_tier="fast",
            quality_tier="high",
            free_tier=FreeTierLimits(rpm=30, tpm=6000, tpd=500000),
        )
        assert "coding" in cap.strengths
        assert "multilingual" in cap.weaknesses
        assert cap.free_tier.rpm == 30


class TestCapabilityMatrix:
    def test_empty_matrix(self) -> None:
        matrix = CapabilityMatrix()
        assert len(matrix.models) == 0

    def test_get_model(self) -> None:
        matrix = CapabilityMatrix(
            models={
                "groq/llama-70b": ModelCapability(
                    provider="groq",
                    strengths=["coding"],
                ),
            }
        )
        model = matrix.get_model("groq/llama-70b")
        assert model is not None
        assert model.provider == "groq"

    def test_get_model_not_found(self) -> None:
        matrix = CapabilityMatrix()
        assert matrix.get_model("nonexistent") is None

    def test_get_provider_models(self) -> None:
        matrix = CapabilityMatrix(
            models={
                "groq/llama-70b": ModelCapability(provider="groq"),
                "groq/llama-8b": ModelCapability(provider="groq"),
                "google/gemini": ModelCapability(provider="google"),
            }
        )
        groq_models = matrix.get_provider_models("groq")
        assert len(groq_models) == 2

        google_models = matrix.get_provider_models("google")
        assert len(google_models) == 1

    def test_get_models_with_strength(self) -> None:
        matrix = CapabilityMatrix(
            models={
                "groq/llama-70b": ModelCapability(
                    provider="groq",
                    strengths=["coding", "reasoning"],
                ),
                "google/gemini": ModelCapability(
                    provider="google",
                    strengths=["long_context", "vision"],
                ),
                "together/llama": ModelCapability(
                    provider="together",
                    strengths=["coding"],
                ),
            }
        )
        coding_models = matrix.get_models_with_strength("coding")
        assert len(coding_models) == 2

        vision_models = matrix.get_models_with_strength("vision")
        assert len(vision_models) == 1

    def test_get_provider_models_empty(self) -> None:
        matrix = CapabilityMatrix()
        assert matrix.get_provider_models("groq") == {}
