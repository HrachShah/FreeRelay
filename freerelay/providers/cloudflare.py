"""
FreeRelay — Cloudflare Workers AI Provider.
Free tier: 10k neurons/day on free Cloudflare account.
Auth: Bearer token (API key).  Requires CLOUDFLARE_ACCOUNT_ID as well.
"""

from __future__ import annotations

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import ProviderError
from freerelay.providers.openai_compat import OpenAICompatibleProvider


class CloudflareProvider(OpenAICompatibleProvider):
    """Cloudflare Workers AI — free 10k neurons/day on free plan."""

    name = "cloudflare"
    base_url = ""          # resolved dynamically from account_id
    supported_features = {"streaming"}
    _default_model = "@cf/meta/llama-3.1-8b-instruct"

    _account_id: str = ""  # populated on first call from settings

    def _get_base_url(self) -> str:
        if not self._account_id:
            from freerelay.config.settings import get_settings
            self._account_id = get_settings().keys.cloudflare_account_id
        if not self._account_id:
            raise ProviderError(
                "CLOUDFLARE_ACCOUNT_ID is required for the Cloudflare provider",
                provider_name=self.name,
            )
        return (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self._account_id}/ai/v1"
        )

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        self.base_url = self._get_base_url()
        return await super().complete(request, api_key)

    async def stream(  # type: ignore[override]
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ):  # type: ignore[return]
        self.base_url = self._get_base_url()
        async for chunk in super().stream(request, api_key):
            yield chunk
