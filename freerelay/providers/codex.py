"""
FreeRelay — Codex Provider (ChatGPT OAuth)
============================================
Proxies requests through the OpenAI Codex API using ChatGPT OAuth tokens.

Auth flow:
1. User authenticates via ChatGPT OAuth (chatgpt.com OAuth flow)
2. JWT access/refresh tokens are obtained and stored
3. Requests go to https://chatgpt.com/backend-api using the session token
4. No OpenAI API key is needed — it piggybacks on the ChatGPT login

Tokens can be provided via:
- CHATGPT_OAUTH_TOKEN env var (raw JWT access token)
- A token file at ~/.codex/auth.json or ~/.openclaw/agents/main/agent/auth-profiles.json

The token file format follows OpenClaw's auth-profiles.json structure:
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "expires_at": 1234567890
}
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError

logger = logging.getLogger("freerelay.codex")

# Possible token file locations
_TOKEN_FILE_PATHS = [
    Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json",
    Path.home() / ".codex" / "auth.json",
]


def _load_token_from_file() -> str:
    """Try to load a ChatGPT OAuth token from known file locations."""
    for path in _TOKEN_FILE_PATHS:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Handle OpenClaw auth-profiles.json format
            if "access_token" in data:
                expires_at = data.get("expires_at", 0)
                if expires_at and expires_at < time.time():
                    logger.warning("ChatGPT OAuth token in %s is expired", path.name)
                    continue
                logger.info("Loaded ChatGPT OAuth token from %s", path)
                return data["access_token"]
            # Handle flat token format
            if "token" in data:
                return data["token"]
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    return ""


def _get_chatgpt_token(explicit_token: str = "") -> str:
    """
    Get a ChatGPT OAuth token.

    Priority:
    1. Explicit token passed by caller
    2. CHATGPT_OAUTH_TOKEN env var (loaded by settings)
    3. Token file on disk
    """
    if explicit_token:
        return explicit_token
    return ""


class CodexProvider(BaseProvider):
    """
    OpenAI Codex provider via ChatGPT OAuth.

    Uses ChatGPT session tokens instead of an OpenAI API key.
    Requests go to chatgpt.com/backend-api.
    """

    name = "codex"
    base_url = "https://chatgpt.com/backend-api"
    supported_features = {"streaming"}

    _default_model = "codex-mini-latest"

    async def complete(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> ChatCompletionResponse:
        # api_key here is the ChatGPT OAuth JWT token
        token = _get_chatgpt_token(api_key) or _load_token_from_file()
        if not token:
            raise ProviderError(
                message=(
                    "No ChatGPT OAuth token found. "
                    "Run 'openclaw configure' to authenticate via ChatGPT OAuth, "
                    "or set CHATGPT_OAUTH_TOKEN in your .env file."
                ),
                status_code=401,
                provider_name=self.name,
                retryable=False,
            )

        payload = self.strip_unsupported_fields(request)
        model = request.model or self._default_model
        # Strip freerelay/ prefix
        if model.startswith("freerelay/"):
            model = model[len("freerelay/") :]
        if model.startswith("codex/"):
            model = model[len("codex/") :]
        payload["model"] = model
        payload.pop("stream", None)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        resp = await self.http_client.post(
            f"{self.base_url}/conversation",
            headers=headers,
            json=payload,
        )

        if resp.status_code == 429:
            raise RateLimitError(provider_name=self.name)
        if resp.status_code == 401:
            raise ProviderError(
                message=(
                    "ChatGPT OAuth token expired or invalid. "
                    "Re-authenticate with 'openclaw configure'."
                ),
                status_code=401,
                provider_name=self.name,
            )
        if resp.status_code >= 400:
            raise ProviderError(
                message=resp.text[:300],
                status_code=resp.status_code,
                provider_name=self.name,
            )

        return ChatCompletionResponse.model_validate(resp.json())

    async def stream(
        self,
        request: ChatCompletionRequest,
        api_key: str,
    ) -> AsyncIterator[str]:
        token = _get_chatgpt_token(api_key) or _load_token_from_file()
        if not token:
            raise ProviderError(
                message="No ChatGPT OAuth token found.",
                status_code=401,
                provider_name=self.name,
            )

        payload = self.strip_unsupported_fields(request)
        model = request.model or self._default_model
        if model.startswith("freerelay/"):
            model = model[len("freerelay/") :]
        if model.startswith("codex/"):
            model = model[len("codex/") :]
        payload["model"] = model
        payload["stream"] = True

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with self.http_client.stream(
            "POST",
            f"{self.base_url}/conversation",
            headers=headers,
            json=payload,
        ) as resp:
            if resp.status_code == 429:
                raise RateLimitError(provider_name=self.name)
            if resp.status_code == 401:
                raise ProviderError(
                    message="ChatGPT OAuth token expired or invalid.",
                    status_code=401,
                    provider_name=self.name,
                )
            if resp.status_code >= 400:
                await resp.aread()
                raise ProviderError(
                    message=resp.text[:300],
                    status_code=resp.status_code,
                    provider_name=self.name,
                )
            async for line in resp.aiter_lines():
                if line.strip():
                    yield f"{line}\n\n"

    def estimate_tokens(self, request: ChatCompletionRequest) -> int:
        return request.estimate_tokens()


def get_codex_token_status() -> dict[str, object]:
    """Check ChatGPT OAuth token status."""
    token = _load_token_from_file()
    if not token:
        return {
            "authenticated": False,
            "message": "No ChatGPT OAuth token found.",
            "setup": "Run 'openclaw configure' or set CHATGPT_OAUTH_TOKEN.",
        }

    # Try to decode JWT to check expiry
    try:
        import base64
        import binascii

        parts = token.split(".")
        if len(parts) == 2:
            payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
            exp = payload.get("exp", 0)
            plan = payload.get("chatgpt_plan_type", "unknown")
            is_expired = exp < time.time() if exp else False

            return {
                "authenticated": True,
                "expired": is_expired,
                "plan_type": plan,
                "expires_at": exp,
                "message": (
                    f"Authenticated via ChatGPT OAuth ({plan} plan)."
                    if not is_expired
                    else "Token expired. Re-authenticate with 'openclaw configure'."
                ),
            }
    except (binascii.Error, ValueError, IndexError, KeyError):
        pass

    return {
        "authenticated": True,
        "message": "ChatGPT OAuth token found (unable to decode JWT).",
    }
