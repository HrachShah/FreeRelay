"""
FreeRelay — OpenClaw Integration Adapter
==========================================
Generates OpenClaw-compatible config and adapts the FreeRelay OpenAI-compatible
endpoint for seamless OpenClaw provider integration.

OpenClaw expects a provider config in ~/.openclaw/openclaw.json:
{
  "models": {
    "providers": {
      "freerelay": {
        "baseUrl": "http://localhost:8000/v1",
        "apiKey": "...",
        "api": "openai-completions",
        "models": [...]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": { "primary": "freerelay/auto" }
    }
  }
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from freerelay.config.settings import Settings


@dataclass
class OpenClawModelEntry:
    """A single model entry for the OpenClaw provider config."""

    id: str
    name: str = ""
    max_tokens: int | None = None
    supports_tools: bool = False
    supports_vision: bool = False
    supports_json: bool = False

    def to_dict(self) -> dict[str, Any]:
        entry: dict[str, Any] = {"id": self.id}
        if self.name:
            entry["name"] = self.name
        if self.max_tokens is not None:
            entry["maxTokens"] = self.max_tokens
        if self.supports_tools:
            entry["supportsTools"] = True
        if self.supports_vision:
            entry["supportsVision"] = True
        if self.supports_json:
            entry["supportsJson"] = True
        return entry


@dataclass
class OpenClawProviderConfig:
    """Complete OpenClaw provider configuration block."""

    base_url: str = "http://localhost:8000/v1"
    api_key: str = ""
    api: str = "openai-completions"
    models: list[OpenClawModelEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseUrl": self.base_url,
            "apiKey": self.api_key,
            "api": self.api,
            "models": [m.to_dict() for m in self.models],
        }


class OpenClawAdapter:
    """
    Builds OpenClaw-compatible provider configuration from FreeRelay's
    runtime state (registered providers, capability matrix).
    """

    def __init__(
        self,
        settings: Settings,
        provider_models: list[dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings
        self._provider_models = provider_models or []

    def build_models(self) -> list[OpenClawModelEntry]:
        """Build the model list for OpenClaw config."""
        models: list[OpenClawModelEntry] = []

        # Always include the auto-routing model
        models.append(
            OpenClawModelEntry(
                id="auto",
                name="FreeRelay Auto (workload-aware routing)",
            )
        )

        # Add provider-specific models
        seen: set[str] = set()
        for pm in self._provider_models:
            provider_name = pm.get("name", "")
            if not provider_name or provider_name in seen:
                continue
            seen.add(provider_name)

            model_id = f"freerelay-{provider_name}"
            models.append(
                OpenClawModelEntry(
                    id=model_id,
                    name=f"FreeRelay → {provider_name.title()}",
                )
            )

        return models

    def build_provider_config(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> OpenClawProviderConfig:
        """Build the full OpenClaw provider config."""
        url = base_url or f"http://{self.settings.host}:{self.settings.port}/v1"
        key = api_key or self.settings.api_key or "not-needed"

        return OpenClawProviderConfig(
            base_url=url,
            api_key=key,
            api="openai-completions",
            models=self.build_models(),
        )

    def generate_config(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate the complete OpenClaw config fragment.
        Merge this into ~/.openclaw/openclaw.json.
        """
        provider = self.build_provider_config(base_url, api_key)

        return {
            "models": {
                "providers": {
                    "freerelay": provider.to_dict(),
                }
            },
            "agents": {
                "defaults": {
                    "model": {
                        "primary": "freerelay/auto",
                    },
                    "models": {
                        "freerelay/auto": {},
                    },
                }
            },
        }

    def generate_setup_commands(
        self,
        base_url: str | None = None,
    ) -> list[str]:
        """Generate CLI commands for OpenClaw setup."""
        url = base_url or f"http://{self.settings.host}:{self.settings.port}/v1"
        return [
            "# Option 1: Use the OpenClaw onboard wizard",
            "openclaw onboard --install-daemon",
            "",
            "# When prompted, choose 'Manual' and enter:",
            f"#   Base URL: {url}",
            "#   API Key:  not-needed",
            "#   Model:    freerelay/auto",
            "",
            "# Option 2: Non-interactive (CI/scripted)",
            "openclaw onboard --non-interactive --accept-risk \\",
            "  --auth-choice apiKey \\",
            "  --token-provider custom \\",
            f'  --custom-base-url "{url}" \\',
            "  --install-daemon --skip-channels --skip-skills",
            "",
            "# Option 3: Set model after onboarding",
            "openclaw models set freerelay/auto",
        ]


def generate_openclaw_config(
    settings: Settings,
    provider_models: list[dict[str, Any]] | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Convenience function to generate OpenClaw config in one call.

    Returns a dict ready to merge into ~/.openclaw/openclaw.json.
    """
    adapter = OpenClawAdapter(settings, provider_models)
    return adapter.generate_config(base_url, api_key)
