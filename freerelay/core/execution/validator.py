"""
FreeRelay — Validation & Repair (§9)
========================================
Runs schema/JSON checks and exposes repair hints.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Sequence

from freerelay.core.models.openai import ChatCompletionResponse
from freerelay.core.routing.policy import RoutingDirective


@dataclass
class ValidationResult:
    schema_pass: bool
    errors: list[str]
    needs_repair: bool


class ValidatorChain:
    """Simple validator chain that enforces schema/JSON rules."""

    def validate(
        self,
        response: ChatCompletionResponse,
        directive: RoutingDirective | None,
    ) -> ValidationResult:
        errors: list[str] = []
        schema_pass = True

        choices = response.choices if response.choices else []
        text = ""
        if choices:
            first = choices[0]
            content = first.message.content
            if isinstance(content, str):
                text = content.strip()
        if directive and directive.enforce_mode in {"json", "schema"}:
            if text:
                try:
                    json.loads(text)
                except json.JSONDecodeError as exc:
                    schema_pass = False
                    errors.append(f"JSON parse failed: {exc}")
            else:
                schema_pass = False
                errors.append("Empty response for JSON validation")

        needs_repair = not schema_pass and bool(directive and (directive.retry_policy or directive.validators))
        return ValidationResult(
            schema_pass=schema_pass,
            errors=errors,
            needs_repair=needs_repair,
        )
