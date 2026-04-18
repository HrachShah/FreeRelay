"""
Routing Engine Factory
======================
Centralized logic for building and configuring the RoutingEngine
with all available providers.
"""

from __future__ import annotations

import logging

from freerelay.config.settings import Settings
from freerelay.core.routing.engine import RoutingEngine

logger = logging.getLogger("freerelay")


def create_routing_engine(settings: Settings) -> RoutingEngine:
    """Build the routing engine and register providers based on mode."""
    from freerelay.providers.google import GoogleProvider
    from freerelay.providers.groq import GroqProvider
    from freerelay.providers.mistral import MistralProvider
    from freerelay.providers.nvidia import NVIDIAProvider
    from freerelay.providers.openrouter import OpenRouterProvider
    from freerelay.providers.together import TogetherProvider

    engine = RoutingEngine(settings)
    keys = settings.keys
    mode = settings.mode

    # Define provider tiers
    free_providers: list[tuple[type, str, int | None]] = [
        (GroqProvider, keys.groq_api_key, 500_000),
        (GoogleProvider, keys.google_ai_key, None),
        (OpenRouterProvider, keys.openrouter_api_key, None),
        (TogetherProvider, keys.together_api_key, None),
        (MistralProvider, keys.mistral_api_key, None),
        (NVIDIAProvider, keys.nvidia_api_key, None),
    ]

    paid_providers: list[tuple[type, str, int | None]] = []

    if keys.openai_api_key:
        from freerelay.providers.openai import OpenAIProvider

        paid_providers.append((OpenAIProvider, keys.openai_api_key, None))

    if keys.anthropic_api_key:
        from freerelay.providers.anthropic import AnthropicProvider

        paid_providers.append((AnthropicProvider, keys.anthropic_api_key, None))

    has_free = any(api_key for _, api_key, _ in free_providers)
    has_paid = any(api_key for _, api_key, _ in paid_providers)

    # Register providers based on mode
    if mode == "free":
        # Only use free providers
        for provider_cls, api_key, daily_limit in free_providers:
            if api_key:
                engine.register_provider(
                    provider=provider_cls(),
                    api_key=api_key,
                    daily_limit=daily_limit,
                    tier="free",
                )
                has_free = True

    elif mode == "paid":
        # Only use paid providers
        for provider_cls, api_key, daily_limit in paid_providers:
            if api_key:
                engine.register_provider(
                    provider=provider_cls(),
                    api_key=api_key,
                    daily_limit=daily_limit,
                    tier="paid",
                )

    else:  # "auto" mode - use free by default, paid for complex tasks
        # Register free providers first
        for provider_cls, api_key, daily_limit in free_providers:
            if api_key:
                engine.register_provider(
                    provider=provider_cls(),
                    api_key=api_key,
                    daily_limit=daily_limit,
                    tier="free",
                )
                has_free = True

        # Also register paid providers for complex tasks
        for provider_cls, api_key, daily_limit in paid_providers:
            if api_key:
                engine.register_provider(
                    provider=provider_cls(),
                    api_key=api_key,
                    daily_limit=daily_limit,
                    tier="paid",
                )
                has_paid = True

    # If no API keys configured, add demo provider
    if not has_free and not has_paid:
        from freerelay.providers.demo import DemoProvider

        engine.register_provider(
            provider=DemoProvider(),
            api_key="demo",
            daily_limit=1000,
            tier="free",
        )
        logger.info("Running in DEMO mode (no API keys configured)")

    # Log the mode
    if mode == "free":
        logger.info("Mode: FREE (using only free providers)")
    elif mode == "paid":
        logger.info("Mode: PAID (using only paid providers)")
    else:
        logger.info("Mode: AUTO (free + paid, routing decides)")

    return engine
