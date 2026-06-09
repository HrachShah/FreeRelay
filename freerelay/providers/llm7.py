"""
FreeRelay — LLM7 Provider
===========================
OpenAI-compatible aggregator. 100 req/hr free, anonymous access works for
basic models (GPT-OSS, Llama 3.1 Turbo, Codestral, GLM-4.6V-Flash).
"""

from __future__ import annotations

from freerelay.providers.openai_compat import OpenAICompatibleProvider


class LLM7Provider(OpenAICompatibleProvider):
    """LLM7.io anonymous-access aggregator."""

    name = "llm7"
    base_url = "https://api.llm7.io/v1"
    supported_features = {"streaming"}
    _default_model = "gpt-4.1"

    def _build_headers(self, api_key: str) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key and api_key != "anon":
            headers["Authorization"] = f"Bearer {api_key}"
        return headers
