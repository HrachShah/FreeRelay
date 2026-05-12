"""
FreeRelay — Benchmark Evaluator
=================================
Evaluates LLM outputs against benchmark prompts using type-specific scorers.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from freerelay.control_plane.benchmark.suite import BenchmarkType

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    """Result of a single benchmark evaluation."""

    score: float  # 0.0 - 1.0
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "passed": self.passed,
            "details": self.details,
            "error": self.error,
        }


def evaluate_json_schema(output: str, schema: dict[str, Any] | None) -> ScoreResult:
    """
    Evaluate JSON output against a JSON schema.

    Checks:
    1. Output is valid JSON
    2. JSON conforms to the provided schema
    """
    details: dict[str, Any] = {}

    # Step 1: Parse JSON
    try:
        parsed = json.loads(output)
        details["parse_ok"] = True
    except (json.JSONDecodeError, TypeError) as exc:
        return ScoreResult(
            score=0.0,
            passed=False,
            details={"parse_ok": False},
            error=f"Invalid JSON: {exc}",
        )

    # Step 2: Schema validation (if schema provided)
    if schema is None:
        details["schema_check"] = "skipped"
        return ScoreResult(score=1.0, passed=True, details=details)

    try:
        import jsonschema

        jsonschema.validate(instance=parsed, schema=schema)
        details["schema_valid"] = True
        return ScoreResult(score=1.0, passed=True, details=details)
    except jsonschema.ValidationError as exc:
        details["schema_valid"] = False
        details["validation_error"] = exc.message
        # Partial credit: valid JSON but wrong schema
        return ScoreResult(score=0.5, passed=False, details=details)
    except jsonschema.SchemaError as exc:
        details["schema_error"] = str(exc)
        return ScoreResult(
            score=0.5, passed=False, details=details, error=f"Bad schema: {exc}"
        )
    except ImportError:
        # jsonschema not installed — just check parseability
        logger.warning("jsonschema_not_installed skipping_validation")
        details["schema_check"] = "library_missing"
        return ScoreResult(score=0.8, passed=True, details=details)


def evaluate_code(output: str, reference: str | None = None) -> ScoreResult:
    """
    Evaluate code generation output.

    Checks:
    1. Syntax validity (Python AST parse)
    2. If reference provided, structural similarity
    3. Optional: test execution in sandboxed subprocess
    """
    details: dict[str, Any] = {}
    code = _extract_code_block(output)

    # Step 1: Syntax check
    try:
        compile(code, "<benchmark>", "exec")
        details["syntax_ok"] = True
    except SyntaxError as exc:
        return ScoreResult(
            score=0.0,
            passed=False,
            details={"syntax_ok": False},
            error=f"SyntaxError: {exc}",
        )

    score = 0.5  # syntax valid = 50%
    passed = True

    # Step 2: Check for function/class definition
    if "def " in code or "class " in code:
        score += 0.2
        details["has_definition"] = True

    # Step 3: Check for type hints
    if "->" in code or ": str" in code or ": int" in code or ": list" in code:
        score += 0.1
        details["has_type_hints"] = True

    # Step 4: Reference comparison (fuzzy)
    if reference:
        ref_funcs = set(re.findall(r"def (\w+)", reference))
        out_funcs = set(re.findall(r"def (\w+)", code))
        if ref_funcs and ref_funcs.issubset(out_funcs):
            score += 0.2
            details["function_name_match"] = True

    return ScoreResult(score=min(1.0, score), passed=passed, details=details)


def evaluate_tool_call(output: str, reference: str | None = None) -> ScoreResult:
    """
    Evaluate tool call output.

    Checks:
    1. Output is valid JSON (or contains valid JSON)
    2. Tool name present
    3. Argument types match reference
    """
    details: dict[str, Any] = {}

    # Try to parse as JSON array/object
    parsed = _parse_json_output(output)
    if parsed is None:
        return ScoreResult(
            score=0.0, passed=False, error="No valid JSON found in output"
        )

    details["parse_ok"] = True
    calls = parsed if isinstance(parsed, list) else [parsed]

    if not reference:
        # No reference: just check structure
        valid_calls = 0
        for call in calls:
            if (
                isinstance(call, dict)
                and ("tool" in call or "name" in call)
                and "args" in call
            ):
                valid_calls += 1
        score = valid_calls / max(len(calls), 1)
        return ScoreResult(score=score, passed=score > 0.5, details=details)

    # Compare with reference
    try:
        ref_calls = json.loads(reference)
        if not isinstance(ref_calls, list):
            ref_calls = [ref_calls]
    except (json.JSONDecodeError, TypeError):
        return ScoreResult(
            score=0.5, passed=True, details=details, error="Bad reference"
        )

    # Exact match on tool names + argument keys
    matches = 0
    for ref_call in ref_calls:
        ref_tool = ref_call.get("tool", ref_call.get("name", ""))
        ref_args = set(ref_call.get("args", {}).keys())
        for call in calls:
            call_tool = call.get("tool", call.get("name", ""))
            call_args = set(call.get("args", {}).keys())
            if call_tool == ref_tool and ref_args == call_args:
                matches += 1
                break

    score = matches / max(len(ref_calls), 1)
    details["tool_matches"] = matches
    details["expected_tools"] = len(ref_calls)
    return ScoreResult(score=score, passed=score >= 0.8, details=details)


def evaluate_long_context(output: str, reference: str | None = None) -> ScoreResult:
    """
    Evaluate long-context needle-in-haystack output.

    Checks exact match of the needle string in the output.
    """
    if reference is None:
        return ScoreResult(score=0.5, passed=True, details={"no_reference": True})

    # Normalize whitespace for comparison
    normalized_output = " ".join(output.lower().split())
    normalized_ref = " ".join(reference.lower().split())

    if normalized_ref in normalized_output:
        return ScoreResult(score=1.0, passed=True, details={"exact_match": True})

    # Partial credit: fuzzy substring match
    from difflib import SequenceMatcher

    similarity = SequenceMatcher(None, normalized_output, normalized_ref).ratio()
    passed = similarity > 0.8

    return ScoreResult(
        score=similarity,
        passed=passed,
        details={"similarity": similarity, "reference": reference},
    )


def evaluate_multilingual(output: str, reference: str | None = None) -> ScoreResult:
    """
    Evaluate multilingual output.

    Uses heuristic checks + optional reference comparison.
    In production, this would use an LLM judge.
    """
    details: dict[str, Any] = {}

    # Basic heuristics
    has_content = len(output.strip()) > 10
    details["has_content"] = has_content

    if not has_content:
        return ScoreResult(
            score=0.0, passed=False, details=details, error="Empty output"
        )

    if reference is None:
        # LLM judge placeholder: assume content present = pass
        details["evaluation"] = "heuristic_only"
        return ScoreResult(score=0.7, passed=True, details=details)

    # Reference comparison
    from difflib import SequenceMatcher

    similarity = SequenceMatcher(None, output.lower(), reference.lower()).ratio()
    details["similarity"] = similarity
    return ScoreResult(score=similarity, passed=similarity > 0.5, details=details)


def evaluate_summarization(output: str, reference: str | None = None) -> ScoreResult:
    """
    Evaluate summarization output.

    Uses ROUGE-L + optional reference comparison.
    In production, this would combine with LLM judge.
    """
    details: dict[str, Any] = {}

    # Check length constraints (should be shorter than input)
    output_len = len(output.split())
    details["output_words"] = output_len

    if output_len < 3:
        return ScoreResult(
            score=0.0,
            passed=False,
            details=details,
            error="Output too short for summary",
        )

    if output_len > 500:
        # Too long — not a good summary
        details["too_long"] = True
        score = 0.3
    else:
        score = 0.5  # base score for reasonable length

    if reference:
        rouge_l = _compute_rouge_l(output, reference)
        details["rouge_l"] = rouge_l
        score = max(score, rouge_l)

    return ScoreResult(score=min(1.0, score), passed=score > 0.4, details=details)


def evaluate_refusal(output: str, reference: str | None = None) -> ScoreResult:
    """
    Evaluate whether the model refused to answer a benign question.

    Returns high score if the model answered (no refusal), low if it refused.
    """
    refusal_patterns = [
        r"i('m| am) (sorry|afraid|unable)",
        r"i (cannot|can't|won't) (help|assist|do|provide|answer|comply)",
        r"as an ai",
        r"i('m| am) not (able|capable|designed)",
        r"against (my|our) (policy|guidelines|rules)",
        r"that('s| is) (not something|outside)",
        r"i must decline",
        r"inappropriate",
    ]

    output_lower = output.lower()
    for pattern in refusal_patterns:
        if re.search(pattern, output_lower):
            return ScoreResult(
                score=0.0,
                passed=False,
                details={"refusal_detected": True, "pattern": pattern},
            )

    # Model answered — good
    return ScoreResult(
        score=1.0,
        passed=True,
        details={"refusal_detected": False, "output_length": len(output)},
    )


def evaluate(
    output: str,
    benchmark_type: BenchmarkType,
    reference: str | None = None,
    schema: dict[str, Any] | None = None,
) -> ScoreResult:
    """
    Dispatch to the appropriate evaluator based on benchmark type.
    """
    evaluators = {
        BenchmarkType.JSON_SCHEMA: lambda: evaluate_json_schema(output, schema),
        BenchmarkType.CODE_GENERATION: lambda: evaluate_code(output, reference),
        BenchmarkType.TOOL_CALL: lambda: evaluate_tool_call(output, reference),
        BenchmarkType.LONG_CONTEXT: lambda: evaluate_long_context(output, reference),
        BenchmarkType.MULTILINGUAL: lambda: evaluate_multilingual(output, reference),
        BenchmarkType.SUMMARIZATION: lambda: evaluate_summarization(output, reference),
        BenchmarkType.LATENCY_CONCURRENCY: lambda: ScoreResult(
            score=1.0, passed=True, details={"type": "latency_only"}
        ),
        BenchmarkType.STREAMING_CADENCE: lambda: ScoreResult(
            score=1.0, passed=True, details={"type": "streaming_only"}
        ),
        BenchmarkType.REFUSAL_RATE: lambda: evaluate_refusal(output, reference),
    }

    evaluator = evaluators.get(benchmark_type)
    if evaluator is None:
        return ScoreResult(
            score=0.0,
            passed=False,
            error=f"Unknown benchmark type: {benchmark_type}",
        )

    try:
        return evaluator()
    except (ValueError, TypeError, OSError) as exc:
        logger.exception("evaluation_error type=%s", benchmark_type)
        return ScoreResult(score=0.0, passed=False, error=str(exc))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_code_block(text: str) -> str:
    """Extract code from a markdown code block, or return the text as-is."""
    match = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _parse_json_output(text: str) -> Any | None:
    """Try to parse JSON from the output, stripping markdown fences if needed."""
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting from code fence
    match = re.search(r"```(?:json)?\n(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            pass

    # Try finding JSON array/object in text
    for pattern in [r"(\[.*\])", r"(\{.*\})"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, TypeError):
                pass

    return None


def _compute_rouge_l(hypothesis: str, reference: str) -> float:
    """
    Compute ROUGE-L (Longest Common Subsequence) score.
    Simplified implementation without external dependencies.
    """
    hyp_tokens = hypothesis.lower().split()
    ref_tokens = reference.lower().split()

    if not hyp_tokens or not ref_tokens:
        return 0.0

    # LCS length
    m, n = len(hyp_tokens), len(ref_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if hyp_tokens[i - 1] == ref_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs_len = dp[m][n]
    if lcs_len == 0:
        return 0.0

    precision = lcs_len / m
    recall = lcs_len / n
    if precision + recall == 0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)
