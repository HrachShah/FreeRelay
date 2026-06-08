"""
FreeRelay — Cohere Provider.
OpenAI-compatibility shim at /v1/chat/completions.
Also supports embeddings (embed-v4.0).
Free tier: limited RPM on trial keys.
"""

from __future__ import annotations

from freerelay.core.models.embeddings import EmbeddingRequest, EmbeddingResponse
from freerelay.providers.base import ProviderError, RateLimitError
from freerelay.providers.openai_compat import OpenAICompatibleProvider


class CohereProvider(OpenAICompatibleProvider):
    """Cohere Command R+: multilingual reasoning, native tool use, embeddings."""

    name = "cohere"
    base_url = "https://api.cohere.ai/compatibility/v1"
    supported_features = {"streaming", "tools", "embeddings"}
    _default_model = "command-r-plus"

    _embed_model = "embed-v4.0"
    _embed_url = "https://api.cohere.ai/v2/embed"

    async def embed(
        self,
        request: EmbeddingRequest,
        api_key: str,
    ) -> EmbeddingResponse:
        texts = request.inputs_as_strings()
        model = request.model if "embed" in request.model else self._embed_model

        payload: dict[str, object] = {
            "texts": texts,
            "model": model,
            "input_type": "search_document",
            "embedding_types": ["float"],
        }

        resp = await self.http_client.post(
            self._embed_url,
            headers=self._build_headers(api_key),
            json=payload,
        )

        if resp.status_code == 429:
            raise RateLimitError(provider_name=self.name)
        if resp.status_code >= 400:
            raise ProviderError(
                message=resp.text[:300],
                status_code=resp.status_code,
                provider_name=self.name,
            )

        data = resp.json()
        # Cohere v2 returns {"embeddings": {"float": [[...], ...]}}
        floats = data.get("embeddings", {}).get("float", [])
        usage = data.get("meta", {}).get("billed_units", {})
        prompt_tokens = usage.get("input_tokens", 0)

        return EmbeddingResponse.from_vectors(
            floats, model=model, prompt_tokens=prompt_tokens
        )
