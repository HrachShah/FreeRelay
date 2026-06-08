"""
FreeRelay — Abstract BaseProvider (§8)
========================================
Every provider implements this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from freerelay.core.models.embeddings import EmbeddingRequest, EmbeddingResponse
from freerelay.core.models.openai import ChatCompletionRequest, ChatCompletionResponse
from freerelay.shared.http_client import get_client


class BaseProvider(ABC):
    """
    Abstract base for all FreeRelay providers.

    Each provider:
    - Translates ChatCompletionRequest to the upstream wire format
    - Sends the HTTP request using the shared connection pool
    - Translates the response back to ChatCompletionResponse
    - Yields raw SSE lines for streaming

    Providers are stateless. Circuit breaking, budget, and retry
    are handled by wrapping layers.
    """

    name: str  # e.g. 'groq'
    base_url: str
    supported_features: set[str]  # 'streaming','tools','logprobs','vision'

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get the shared HTTP client with connection pooling."""
        return get_client()

    @abstractmethod
    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        """
        Execute a non-streaming chat completion.

        Args:
            request: Validated chat completion request.
            api_key: API key for this provider.

        Returns:
            ChatCompletionResponse in OpenAI format.

        Raises:
            ProviderError: On upstream failure.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        """
        Execute a streaming chat completion.

        Yields raw SSE lines (e.g., 'data: {...}\\n\\n').
        The caller is responsible for forwarding these to the client.

        Args:
            request: Validated chat completion request.
            api_key: API key for this provider.

        Yields:
            SSE data lines as strings.

        Raises:
            ProviderError: On upstream failure.
        """
        ...
        yield ""  # type: ignore[misc]  # pragma: no cover

    @abstractmethod
    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        """
        Estimate token count for a request BEFORE sending.
        Used by the budget forecaster.

        Simple heuristic: count chars / 4 for each message.
        """
        ...

    async def embed(
        self,
        request: EmbeddingRequest,
        api_key: str,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for *request*.

        Default implementation raises ``ProviderError``.  Override in
        providers that support the ``"embeddings"`` feature flag.
        """
        raise ProviderError(
            f"{self.name} does not support embeddings",
            status_code=400,
            provider_name=self.name,
        )

    def strip_unsupported_fields(
        self, request: ChatCompletionRequest
    ) -> dict[str, object]:
        """
        Convert request to dict, stripping fields this provider doesn't support.
        """
        data = request.model_dump(exclude_none=True)

        if "logprobs" not in self.supported_features:
            data.pop("logprobs", None)
            data.pop("top_logprobs", None)

        if "tools" not in self.supported_features:
            data.pop("tools", None)
            data.pop("tool_choice", None)

        if "logit_bias" not in self.supported_features:
            data.pop("logit_bias", None)

        return data


class ProviderError(Exception):
    """Raised when a provider encounters an error."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        provider_name: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider_name = provider_name
        self.retryable = retryable


class RateLimitError(ProviderError):
    """Raised on 429 responses."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        provider_name: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=429,
            provider_name=provider_name,
            retryable=True,
        )
        self.retry_after = retry_after
