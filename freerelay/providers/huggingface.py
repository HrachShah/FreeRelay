"""
FreeRelay — HuggingFace Inference Router Provider.
Free tier: limited requests on HuggingFace free account.
OpenAI-compatible router at https://router.huggingface.co/v1.
Also supports embeddings.
"""

from __future__ import annotations

from freerelay.core.models.embeddings import EmbeddingRequest, EmbeddingResponse
from freerelay.providers.base import ProviderError, RateLimitError
from freerelay.providers.openai_compat import OpenAICompatibleProvider


class HuggingFaceProvider(OpenAICompatibleProvider):
    """HuggingFace Inference Router — diverse model selection."""

    name = "huggingface"
    base_url = "https://router.huggingface.co/v1"
    supported_features = {"streaming", "embeddings"}
    _default_model = "meta-llama/Llama-3.1-8B-Instruct"

    _embed_model = "sentence-transformers/all-MiniLM-L6-v2"

    async def embed(
        self,
        request: EmbeddingRequest,
        api_key: str,
    ) -> EmbeddingResponse:
        texts = request.inputs_as_strings()
        default_model = "text-embedding-3-small"
        model = request.model if request.model != default_model else self._embed_model

        payload: dict[str, object] = {
            "input": texts,
            "model": model,
        }

        resp = await self.http_client.post(
            f"{self.base_url}/embeddings",
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
        vectors = [item["embedding"] for item in data.get("data", [])]
        usage = data.get("usage", {})
        return EmbeddingResponse.from_vectors(
            vectors, model=model, prompt_tokens=usage.get("prompt_tokens", 0)
        )
