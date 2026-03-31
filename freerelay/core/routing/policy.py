"""
FreeRelay — Routing Policy DSL Interpreter (§14.3)
==================================================
Evaluates rich routing rules against workload profiles, budget cues, and tenant policy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("freerelay.policy")


def _eval_condition_context(condition: str, context: dict[str, Any]) -> bool:
    if not condition:
        return False
    try:
        return bool(eval(condition, {"__builtins__": {}}, context))
    except Exception:
        logger.warning("Failed to evaluate condition: %s", condition)
        return False


def _eval_condition(
    condition: str,
    intent_or_context: str | dict[str, Any],
    prompt_tokens: int | None = None,
) -> bool:
    if isinstance(intent_or_context, dict):
        context = intent_or_context
    else:
        context = {"intent": intent_or_context, "prompt_tokens": prompt_tokens or 0}
    return _eval_condition_context(condition, context)


@dataclass
class RoutingDirective:
    prefer: list[str] = field(default_factory=list)
    require: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    validators: list[str] = field(default_factory=list)
    fanout: int | None = None
    retry_policy: str | None = None
    set_temperature: float | None = None
    enforce_mode: str | None = None
    require_hedging: str | None = None
    human_gate: bool = False
    policy_weight: float = 1.0


@dataclass
class RoutingRule:
    name: str
    condition: str
    prefer: list[str] = field(default_factory=list)
    require: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    validators: list[str] = field(default_factory=list)
    fanout: int | None = None
    retry_policy: str | None = None
    set_temperature: float | None = None
    enforce_mode: str | None = None
    require_hedging: str | None = None
    human_gate: bool = False
    policy_weight: float = 1.0
    fallback: str = "any"

    @property
    def directive(self) -> RoutingDirective:
        return RoutingDirective(
            prefer=self.prefer,
            require=self.require,
            exclude=self.exclude,
            validators=self.validators,
            fanout=self.fanout,
            retry_policy=self.retry_policy,
            set_temperature=self.set_temperature,
            enforce_mode=self.enforce_mode,
            require_hedging=self.require_hedging,
            human_gate=self.human_gate,
            policy_weight=self.policy_weight,
        )


@dataclass
class RoutingPolicy:
    """Collection of routing rules loaded from YAML."""

    version: int = 1
    rules: list[RoutingRule] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> RoutingPolicy:
        """Load routing policy from a YAML file."""
        path = Path(path)
        if not path.exists():
            logger.warning("Routing rules file not found: %s", path)
            return cls()

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        rules: list[RoutingRule] = []
        for rule_data in data.get("rules", []):
            actions = {}
            for entry in rule_data.get("actions", []):
                if isinstance(entry, dict):
                    actions.update(entry)

            rules.append(
                RoutingRule(
                    name=rule_data.get("name", ""),
                    condition=rule_data.get("condition", ""),
                    prefer=actions.get("prefer", rule_data.get("prefer", [])),
                    require=actions.get("require", rule_data.get("require", [])),
                    exclude=actions.get("exclude", rule_data.get("exclude", [])),
                    validators=actions.get("validators", rule_data.get("validators", [])),
                    fanout=actions.get("fanout", rule_data.get("fanout")),
                    retry_policy=actions.get(
                        "retry_policy", rule_data.get("retry_policy")
                    ),
                    set_temperature=actions.get(
                        "set_temperature", rule_data.get("set_temperature")
                    ),
                    enforce_mode=actions.get(
                        "enforce_mode", rule_data.get("enforce_mode")
                    ),
                    require_hedging=actions.get(
                        "require_hedging", rule_data.get("require_hedging")
                    ),
                    human_gate=actions.get("human_gate", rule_data.get("human_gate", False)),
                    policy_weight=actions.get(
                        "policy_weight", rule_data.get("policy_weight", 1.0)
                    ),
                    fallback=rule_data.get("fallback", "any"),
                )
            )

        return cls(version=data.get("version", 1), rules=rules)

    def apply(
        self,
        context: dict[str, Any],
        available_providers: list[str],
    ) -> tuple[list[str], RoutingDirective]:
        """Reorder providers and surface the matching directive."""
        for rule in self.rules:
            if self._eval_condition(rule.condition, context):
                directive = rule.directive
                logger.info(
                    "Routing rule %s matched → %s",
                    rule.name,
                    ", ".join(directive.prefer or ["(no prefer)"]),
                )
                ordered = self._reorder_providers(
                    available_providers, directive.prefer, directive.exclude
                )
                return ordered, directive
        return available_providers, RoutingDirective()

    def _eval_condition(self, condition: str, context: dict[str, Any]) -> bool:
        return _eval_condition_context(condition, context)

    def _reorder_providers(
        self,
        providers: list[str],
        prefer: list[str],
        exclude: list[str],
    ) -> list[str]:
        filtered = [p for p in providers if p not in exclude]
        preferred = [p for p in prefer if p in filtered]
        remaining = [p for p in filtered if p not in preferred]
        return preferred + remaining

    @classmethod
    def default(cls) -> RoutingPolicy:
        return cls()


def apply_routing_policy(
    policy: RoutingPolicy,
    request: Any,
    intent: str,
    available_providers: list[str],
) -> list[str]:
    context = {
        "intent": intent,
        "prompt_tokens": getattr(request, "prompt_tokens", 0) or 0,
    }
    ordered, _ = policy.apply(context, available_providers)
    return ordered
