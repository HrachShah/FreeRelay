"""
FreeRelay — EmbeddingsRouter: /v1/embeddings routing logic.

Selects the best healthy provider that supports embeddings, tries the
requested model first, falls back across all embeddings-capable slots.
"""

from __future__ import annotations

import logging

from freerelay.core.models.embeddings import EmbeddingRequest, EmbeddingResponse
from freerelay.providers.base import ProviderError, RateLimitError

logger = logging.getLogger("freerelay.embeddings_router")

# Map of model prefix / exact name → preferred provider name
_MODEL_PROVIDER_HINTS: dict[str, str] = {
    "embed-v4": "cohere",
    "embed-english": "cohere",
    "embed-multilingual": "cohere",
    "text-embedding-004": "google",
    "mistral-embed": "mistral",
    "nvidia": "nvidia",
    "sentence-transformers": "huggingface",
}


class EmbeddingsRouter:
    """
    Routes embedding requests across providers.

    Used by the main RoutingEngine — not a standalone engine.
    Takes the engine's slot list and circuit state directly.
    """

    def __init__(self, engine: object) -> None:  # type: ignore[type-arg]
        # Avoid circular import — engine is RoutingEngine at runtime
        self._engine = engine

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Route an embedding request to the best available provider."""
        from freerelay.core.routing.engine import RoutingEngine  # noqa: PLC0415

        engine: RoutingEngine = self._engine  # type: ignore[assignment]

        # Collect embeddings-capable slots
        capable_slots = [
            slot
            for slot in engine.slots
            if "embeddings" in slot.provider.supported_features
        ]

        if not capable_slots:
            raise ProviderError(
                "No providers with embeddings support configured. "
                "Add COHERE_API_KEY, HUGGINGFACE_API_KEY, MISTRAL_API_KEY, "
                "NVIDIA_API_KEY, GOOGLE_AI_KEY, or OPENAI_API_KEY.",
                status_code=503,
            )

        # Sort: prefer provider hinted by the model name
        model_lower = request.model.lower()
        preferred_name: str | None = None
        for prefix, pname in _MODEL_PROVIDER_HINTS.items():
            if prefix in model_lower:
                preferred_name = pname
                break

        def _slot_priority(slot: object) -> int:  # type: ignore[type-arg]
            from freerelay.core.routing.engine import ProviderSlot  # noqa: PLC0415
            s: ProviderSlot = slot  # type: ignore[assignment]
            return 0 if s.provider.name == preferred_name else 1

        ordered = sorted(capable_slots, key=_slot_priority)

        last_error: Exception | None = None
        for slot in ordered:
            from freerelay.core.routing.engine import ProviderSlot  # noqa: PLC0415
            s: ProviderSlot = slot  # type: ignore[assignment]

            if not await s.circuit.can_execute():
                continue

            try:
                response = await s.provider.embed(request, s.key_pool.next())  # type: ignore[attr-defined]
                await s.circuit.record_success()
                n_vecs = len(response.data)
                logger.info("Embeddings via %s (%d vectors)", s.provider.name, n_vecs)
                return response
            except RateLimitError as e:
                await s.circuit.record_failure(429)
                logger.warning("%s rate limited (embeddings)", s.provider.name)
                last_error = e
            except ProviderError as e:
                await s.circuit.record_failure(e.status_code)
                logger.warning("%s embeddings error: %s", s.provider.name, str(e)[:100])
                last_error = e
            except Exception as e:
                await s.circuit.record_failure(None)
                logger.exception("%s embeddings unexpected error", s.provider.name)
                last_error = e

        raise ProviderError(
            f"All embedding providers failed. Last error: {last_error}",
            status_code=503,
        )
