"""
FreeRelay Data Plane — Policy DSL Interpreter (§5.3)
=======================================================
Pre-parsed at load time, O(policies) matching at runtime.
Supports the full DSL v2 grammar for routing policies.
"""

from __future__ import annotations

import logging
import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("freerelay.data_plane.policy")


class Operator(StrEnum):
    """Comparison operators for policy conditions."""
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    MATCHES = "matches"


_OPS: dict[Operator, Callable[[Any, Any], bool]] = {
    Operator.EQ: operator.eq,
    Operator.NEQ: operator.ne,
    Operator.GT: operator.gt,
    Operator.GTE: operator.ge,
    Operator.LT: operator.lt,
    Operator.LTE: operator.le,
    Operator.IN: lambda a, b: a in b,
    Operator.NOT_IN: lambda a, b: a not in b,
    Operator.CONTAINS: lambda a, b: b in a if isinstance(a, (list, str)) else False,
    Operator.MATCHES: lambda a, b: __import__("re").search(str(b), str(a)) is not None,
}


@dataclass
class Condition:
    """A single condition in a policy rule."""
    field: str
    op: Operator
    value: Any

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate this condition against a context dict."""
        actual = self._resolve_field(context, self.field)
        if actual is None:
            return False
        try:
            op_func = _OPS.get(self.op)
            if op_func is None:
                return False
            return op_func(actual, self.value)
        except Exception:
            return False

    def _resolve_field(self, context: dict[str, Any], path: str) -> Any:
        """Resolve a dot-notation field path in the context."""
        parts = path.split(".")
        current = context
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        return current


@dataclass
class PolicyAction:
    """Action to take when a policy matches."""
    prefer: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    set_temperature: float | None = None
    set_max_tokens: int | None = None
    enforce_mode: str | None = None
    weight: float = 1.0
    description: str = ""


@dataclass
class Policy:
    """A single routing policy with conditions and action."""
    name: str
    priority: int = 0
    conditions: list[Condition] = field(default_factory=list)
    condition_mode: str = "all"  # "all" or "any"
    action: PolicyAction = field(default_factory=PolicyAction)

    def matches(self, context: dict[str, Any]) -> bool:
        """Check if this policy matches the given context."""
        if not self.conditions:
            return False

        if self.condition_mode == "any":
            return any(c.evaluate(context) for c in self.conditions)

        return all(c.evaluate(context) for c in self.conditions)


@dataclass
class RoutingDirective:
    """Directive produced by policy matching."""
    prefer: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    set_temperature: float | None = None
    set_max_tokens: int | None = None
    enforce_mode: str | None = None
    policy_weight: float = 1.0
    matched_policy: str = ""


class PolicyDSL:
    """
    Policy DSL interpreter for routing rules.

    Loads YAML policy definitions and evaluates them against workload context.

    DSL v2 grammar:
      policies:
        - name: "policy_name"
          priority: 10
          conditions:
            - field: "workload.task_family"
              op: "eq"
              value: "coding"
          condition_mode: "all"  # or "any"
          action:
            prefer: ["groq"]
            avoid: ["together"]
            set_temperature: 0.0
            enforce_mode: "json"
            weight: 1.5
    """

    def __init__(self) -> None:
        self._policies: list[Policy] = []

    def load_policy(self, yaml_str: str) -> list[Policy]:
        """
        Parse policies from YAML string.

        Args:
            yaml_str: YAML string with policy definitions.

        Returns:
            List of parsed Policy objects.
        """
        try:
            data = yaml.safe_load(yaml_str)
            if not data or "policies" not in data:
                return []

            policies: list[Policy] = []
            for raw in data["policies"]:
                policy = self._parse_policy(raw)
                if policy:
                    policies.append(policy)

            self._policies = sorted(policies, key=lambda p: p.priority, reverse=True)
            logger.info("Loaded %d routing policies", len(self._policies))
            return self._policies

        except (yaml.YAMLError, OSError):
            logger.exception("Failed to parse policy YAML")
            return []

    def load_policy_file(self, path: Path) -> list[Policy]:
        """Load policies from a YAML file."""
        try:
            with open(path, encoding="utf-8") as f:
                return self.load_policy(f.read())
        except FileNotFoundError:
            logger.warning("Policy file not found: %s", path)
            return []
        except Exception:
            logger.exception("Failed to load policy file: %s", path)
            return []

    def _parse_policy(self, raw: dict[str, Any]) -> Policy | None:
        """Parse a single policy from raw dict."""
        try:
            name = raw.get("name", "unnamed")
            priority = raw.get("priority", 0)
            condition_mode = raw.get("condition_mode", "all")

            conditions: list[Condition] = []
            for cond_raw in raw.get("conditions", []):
                op_str = cond_raw.get("op", "eq")
                try:
                    op = Operator(op_str)
                except ValueError:
                    logger.warning("Unknown operator: %s", op_str)
                    continue
                conditions.append(Condition(
                    field=cond_raw["field"],
                    op=op,
                    value=cond_raw["value"],
                ))

            action_raw = raw.get("action", {})
            action = PolicyAction(
                prefer=action_raw.get("prefer", []),
                avoid=action_raw.get("avoid", []),
                set_temperature=action_raw.get("set_temperature"),
                set_max_tokens=action_raw.get("set_max_tokens"),
                enforce_mode=action_raw.get("enforce_mode"),
                weight=action_raw.get("weight", 1.0),
                description=action_raw.get("description", ""),
            )

            return Policy(
                name=name,
                priority=priority,
                conditions=conditions,
                condition_mode=condition_mode,
                action=action,
            )
        except Exception:
            logger.exception("Failed to parse policy: %s", raw)
            return None

    def match_conditions(self, policy: Policy, context: dict[str, Any]) -> bool:
        """Check if a policy's conditions match the given context."""
        return policy.matches(context)

    def apply(
        self,
        context: dict[str, Any],
        candidates: list[str],
    ) -> tuple[list[str], RoutingDirective]:
        """
        Apply policies to reorder candidates and produce a directive.

        Args:
            context: Workload context dict.
            candidates: List of candidate provider names.

        Returns:
            (reordered_candidates, directive) tuple.
        """
        directive = RoutingDirective()

        for policy in self._policies:
            if policy.matches(context):
                logger.debug("Policy '%s' matched", policy.name)
                directive.matched_policy = policy.name

                if policy.action.prefer:
                    directive.prefer = policy.action.prefer
                if policy.action.avoid:
                    directive.avoid = policy.action.avoid
                if policy.action.set_temperature is not None:
                    directive.set_temperature = policy.action.set_temperature
                if policy.action.set_max_tokens is not None:
                    directive.set_max_tokens = policy.action.set_max_tokens
                if policy.action.enforce_mode is not None:
                    directive.enforce_mode = policy.action.enforce_mode
                directive.policy_weight = policy.action.weight
                break  # First (highest priority) match wins

        # Reorder candidates based on directive
        reordered = self._reorder(candidates, directive)
        return reordered, directive

    def _reorder(
        self,
        candidates: list[str],
        directive: RoutingDirective,
    ) -> list[str]:
        """Reorder candidate list based on prefer/avoid directives."""
        preferred = [c for c in directive.prefer if c in candidates]
        avoided = set(directive.avoid)
        remaining = [c for c in candidates if c not in preferred and c not in avoided]

        return preferred + remaining
