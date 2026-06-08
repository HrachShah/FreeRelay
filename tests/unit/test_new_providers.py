"""Tests for new OpenAI-compatible provider classes."""

from __future__ import annotations

import pytest

from freerelay.providers.cerebras import CerebrasProvider
from freerelay.providers.cloudflare import CloudflareProvider
from freerelay.providers.cohere import CohereProvider
from freerelay.providers.github_models import GitHubModelsProvider
from freerelay.providers.huggingface import HuggingFaceProvider
from freerelay.providers.zai import ZaiProvider


def test_cerebras_defaults() -> None:
    p = CerebrasProvider()
    assert p.name == "cerebras"
    assert "cerebras.ai" in p.base_url
    assert "streaming" in p.supported_features


def test_cohere_defaults() -> None:
    p = CohereProvider()
    assert p.name == "cohere"
    assert "embeddings" in p.supported_features
    assert "tools" in p.supported_features


def test_github_models_defaults() -> None:
    p = GitHubModelsProvider()
    assert p.name == "github_models"
    assert "github.ai" in p.base_url
    assert "vision" in p.supported_features


def test_huggingface_defaults() -> None:
    p = HuggingFaceProvider()
    assert p.name == "huggingface"
    assert "embeddings" in p.supported_features


def test_zai_defaults() -> None:
    p = ZaiProvider()
    assert p.name == "zai"
    assert "z.ai" in p.base_url


def test_cloudflare_raises_without_account_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cloudflare provider should raise ProviderError if account_id is missing."""
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)

    from unittest.mock import patch

    from freerelay.providers.base import ProviderError

    p = CloudflareProvider()
    # Mock settings to return empty account id
    with patch("freerelay.config.settings.get_settings") as mock_settings:
        mock_settings.return_value.keys.cloudflare_account_id = ""
        with pytest.raises(ProviderError, match="CLOUDFLARE_ACCOUNT_ID"):
            p._get_base_url()
