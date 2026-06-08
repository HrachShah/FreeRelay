"""
FreeRelay — GitHub Models Provider.
Free tier: rate-limited access to GPT-4o, o1, Llama, Mistral, etc.
Auth: GitHub PAT (classic or fine-grained with no required scopes).
"""

from __future__ import annotations

from freerelay.providers.openai_compat import OpenAICompatibleProvider


class GitHubModelsProvider(OpenAICompatibleProvider):
    """GitHub Models inference endpoint — free for personal GitHub accounts."""

    name = "github_models"
    base_url = "https://models.github.ai/inference"
    supported_features = {"streaming", "tools", "vision"}
    _default_model = "openai/gpt-4o-mini"
