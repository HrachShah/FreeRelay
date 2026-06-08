"""
FreeRelay — OpenAI-compatible Embeddings wire format (Pydantic v2).

Covers /v1/embeddings request and response shapes so any provider's embed()
method can return a fully typed, OpenAI-compatible response.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    """POST /v1/embeddings request body."""

    input: str | list[str] | list[int] | list[list[int]]
    model: str = "text-embedding-3-small"
    encoding_format: Literal["float", "base64"] = "float"
    dimensions: int | None = None
    user: str | None = None

    def inputs_as_strings(self) -> list[str]:
        """Normalise *input* to a list of strings for providers that need it."""
        if isinstance(self.input, str):
            return [self.input]
        if isinstance(self.input, list):
            if not self.input:
                return []
            first = self.input[0]
            if isinstance(first, str):
                return list(self.input)  # type: ignore[arg-type]
            # token arrays — join as space-separated tokens (best-effort)
            if isinstance(first, int):
                return [" ".join(str(t) for t in self.input)]  # type: ignore[arg-type]
            # list[list[int]]
            return [" ".join(str(t) for t in seq) for seq in self.input]  # type: ignore[arg-type]
        return [str(self.input)]


class EmbeddingData(BaseModel):
    """A single embedding vector result."""

    object: Literal["embedding"] = "embedding"
    index: int
    embedding: list[float]


class EmbeddingUsage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingResponse(BaseModel):
    """POST /v1/embeddings response body (OpenAI wire format)."""

    object: Literal["list"] = "list"
    data: list[EmbeddingData] = Field(default_factory=list)
    model: str
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)

    @classmethod
    def from_vectors(
        cls,
        vectors: list[list[float]],
        model: str,
        prompt_tokens: int = 0,
    ) -> EmbeddingResponse:
        return cls(
            model=model,
            data=[
                EmbeddingData(index=i, embedding=vec)
                for i, vec in enumerate(vectors)
            ],
            usage=EmbeddingUsage(
                prompt_tokens=prompt_tokens,
                total_tokens=prompt_tokens,
            ),
        )
