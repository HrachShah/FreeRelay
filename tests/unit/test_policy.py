"""
Tests — Routing Policy DSL
=============================
Verify YAML policy loading and condition evaluation.
"""

import tempfile
from pathlib import Path

from freerelay.core.models.openai import ChatCompletionRequest
from freerelay.core.routing.policy import (
    RoutingPolicy,
    RoutingRule,
    _eval_condition,
    apply_routing_policy,
)


class TestEvalCondition:
    def test_intent_equality(self) -> None:
        assert _eval_condition("intent == 'coding'", "coding", 100) is True
        assert _eval_condition("intent == 'coding'", "chat", 100) is False

    def test_intent_inequality(self) -> None:
        assert _eval_condition("intent != 'coding'", "chat", 100) is True
        assert _eval_condition("intent != 'coding'", "coding", 100) is False

    def test_token_comparison(self) -> None:
        assert _eval_condition("prompt_tokens > 50000", "general", 60000) is True
        assert _eval_condition("prompt_tokens > 50000", "general", 40000) is False
        assert _eval_condition("prompt_tokens < 500", "chat", 400) is True
        assert _eval_condition("prompt_tokens < 500", "chat", 600) is False

    def test_and_conjunction(self) -> None:
        cond = "intent == 'chat' and prompt_tokens < 500"
        assert _eval_condition(cond, "chat", 400) is True
        assert _eval_condition(cond, "chat", 600) is False
        assert _eval_condition(cond, "coding", 400) is False

    def test_or_conjunction(self) -> None:
        cond = "intent == 'coding' or intent == 'math'"
        assert _eval_condition(cond, "coding", 100) is True
        assert _eval_condition(cond, "math", 100) is True
        assert _eval_condition(cond, "chat", 100) is False

    def test_empty_condition(self) -> None:
        assert _eval_condition("", "coding", 100) is False

    def test_invalid_condition(self) -> None:
        assert _eval_condition("invalid syntax here", "coding", 100) is False


class TestRoutingPolicy:
    def test_from_yaml(self) -> None:
        yaml_content = """
version: 1
rules:
  - name: coding_tasks
    condition: "intent == 'coding'"
    prefer: [groq/llama-70b]
    fallback: any
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            f.flush()
            policy = RoutingPolicy.from_yaml(f.name)

        Path(f.name).unlink()
        assert len(policy.rules) == 1
        assert policy.rules[0].name == "coding_tasks"
        assert policy.rules[0].prefer == ["groq/llama-70b"]

    def test_from_nonexistent_file(self) -> None:
        policy = RoutingPolicy.from_yaml("/nonexistent/path.yaml")
        assert len(policy.rules) == 0

    def test_default_policy(self) -> None:
        policy = RoutingPolicy.default()
        assert len(policy.rules) == 0
        assert policy.version == 1


class TestApplyRoutingPolicy:
    def test_no_rules_returns_original(self) -> None:
        policy = RoutingPolicy.default()
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = apply_routing_policy(
            policy,
            req,
            "chat",
            ["groq", "google", "openrouter"],
        )
        assert result == ["groq", "google", "openrouter"]

    def test_matching_rule_reorders(self) -> None:
        policy = RoutingPolicy(
            rules=[
                RoutingRule(
                    name="coding",
                    condition="intent == 'coding'",
                    prefer=["together", "groq"],
                    fallback="any",
                ),
            ]
        )
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Write Python code"}],
        )
        result = apply_routing_policy(
            policy,
            req,
            "coding",
            ["groq", "google", "together"],
        )
        assert result[0] == "together"
        assert result[1] == "groq"
        assert result[2] == "google"

    def test_non_matching_rule_returns_original(self) -> None:
        policy = RoutingPolicy(
            rules=[
                RoutingRule(
                    name="coding",
                    condition="intent == 'coding'",
                    prefer=["groq"],
                    fallback="any",
                ),
            ]
        )
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Hello"}],
        )
        result = apply_routing_policy(
            policy,
            req,
            "chat",
            ["google", "openrouter"],
        )
        assert result == ["google", "openrouter"]

    def test_preferred_not_in_available_skipped(self) -> None:
        policy = RoutingPolicy(
            rules=[
                RoutingRule(
                    name="coding",
                    condition="intent == 'coding'",
                    prefer=["mistral", "groq"],
                    fallback="any",
                ),
            ]
        )
        req = ChatCompletionRequest(
            messages=[{"role": "user", "content": "Write Python code"}],
        )
        result = apply_routing_policy(
            policy,
            req,
            "coding",
            ["groq", "google"],
        )
        assert result[0] == "groq"
        assert "mistral" not in result
