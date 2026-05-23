"""
FreeRelay — Benchmark Suite Definition
=========================================
Defines benchmark types, prompt templates, and suite loading logic.
Supports full suite runs and 10% spot-check sampling.
"""

from __future__ import annotations

import enum
import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BENCHMARK_SUITE_DIR = Path("tests/benchmark_suite/prompts")


class BenchmarkType(enum.StrEnum):
    """Benchmark categories for provider evaluation."""

    JSON_SCHEMA = "json_schema"
    CODE_GENERATION = "code_generation"
    TOOL_CALL = "tool_call"
    LONG_CONTEXT = "long_context"
    MULTILINGUAL = "multilingual"
    SUMMARIZATION = "summarization"
    LATENCY_CONCURRENCY = "latency_concurrency"
    STREAMING_CADENCE = "streaming_cadence"
    REFUSAL_RATE = "refusal_rate"


@dataclass
class BenchmarkPrompt:
    """A single benchmark prompt with expected output and evaluation metadata."""

    id: str
    type: BenchmarkType
    prompt: str
    reference_answer: str | None = None
    schema: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    difficulty: str = "medium"  # easy | medium | hard
    timeout_s: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "prompt": self.prompt,
            "reference_answer": self.reference_answer,
            "schema": self.schema,
            "tags": self.tags,
            "difficulty": self.difficulty,
            "timeout_s": self.timeout_s,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkPrompt:
        return cls(
            id=data["id"],
            type=BenchmarkType(data["type"]),
            prompt=data["prompt"],
            reference_answer=data.get("reference_answer"),
            schema=data.get("schema"),
            tags=data.get("tags", []),
            difficulty=data.get("difficulty", "medium"),
            timeout_s=data.get("timeout_s", 30.0),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Placeholder prompts (3-5 per benchmark type)
# ---------------------------------------------------------------------------

_PLACEHOLDER_PROMPTS: list[BenchmarkPrompt] = [
    # ── JSON_SCHEMA ────────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="json_schema_001",
        type=BenchmarkType.JSON_SCHEMA,
        prompt='Extract the following into JSON: "John Doe, age 32, lives in Berlin, works as a software engineer."',
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "city": {"type": "string"},
                "occupation": {"type": "string"},
            },
            "required": ["name", "age", "city", "occupation"],
        },
        reference_answer='{"name": "John Doe", "age": 32, "city": "Berlin", "occupation": "software engineer"}',
        tags=["extraction", "structured"],
    ),
    BenchmarkPrompt(
        id="json_schema_002",
        type=BenchmarkType.JSON_SCHEMA,
        prompt="Parse this product review into structured JSON: 'The iPhone 15 Pro is amazing. Battery life could be better though. 4/5 stars.'",
        schema={
            "type": "object",
            "properties": {
                "product": {"type": "string"},
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "negative", "mixed"],
                },
                "rating": {"type": "number"},
                "pros": {"type": "array", "items": {"type": "string"}},
                "cons": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["product", "sentiment", "rating"],
        },
        tags=["extraction", "sentiment"],
    ),
    BenchmarkPrompt(
        id="json_schema_003",
        type=BenchmarkType.JSON_SCHEMA,
        prompt="Return a JSON object with the Fibonacci sequence for the first 10 numbers.",
        schema={
            "type": "object",
            "properties": {
                "sequence": {"type": "array", "items": {"type": "integer"}},
                "count": {"type": "integer"},
            },
            "required": ["sequence", "count"],
        },
        reference_answer='{"sequence": [0,1,1,2,3,5,8,13,21,34], "count": 10}',
        tags=["math", "structured"],
    ),
    BenchmarkPrompt(
        id="json_schema_004",
        type=BenchmarkType.JSON_SCHEMA,
        prompt="Extract all entities from: 'Apple CEO Tim Cook announced the new MacBook Pro at WWDC 2024 in Cupertino.'",
        schema={
            "type": "object",
            "properties": {
                "organizations": {"type": "array", "items": {"type": "string"}},
                "people": {"type": "array", "items": {"type": "string"}},
                "products": {"type": "array", "items": {"type": "string"}},
                "events": {"type": "array", "items": {"type": "string"}},
                "locations": {"type": "array", "items": {"type": "string"}},
            },
        },
        tags=["ner", "extraction"],
    ),
    # ── CODE_GENERATION ────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="code_gen_001",
        type=BenchmarkType.CODE_GENERATION,
        prompt="Write a Python function `merge_sorted(a: list[int], b: list[int]) -> list[int]` that merges two sorted lists into one sorted list. Include type hints.",
        reference_answer="def merge_sorted(a: list[int], b: list[int]) -> list[int]:\n    result = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n        if a[i] <= b[j]:\n            result.append(a[i]); i += 1\n        else:\n            result.append(b[j]); j += 1\n    result.extend(a[i:])\n    result.extend(b[j:])\n    return result",
        tags=["python", "algorithms"],
    ),
    BenchmarkPrompt(
        id="code_gen_002",
        type=BenchmarkType.CODE_GENERATION,
        prompt="Write a TypeScript function that validates an email address using regex. Return true/false.",
        tags=["typescript", "validation"],
        difficulty="easy",
    ),
    BenchmarkPrompt(
        id="code_gen_003",
        type=BenchmarkType.CODE_GENERATION,
        prompt="Implement a LRU cache in Python with O(1) get and put operations. Class name: LRUCache.",
        tags=["python", "data-structures"],
        difficulty="hard",
    ),
    BenchmarkPrompt(
        id="code_gen_004",
        type=BenchmarkType.CODE_GENERATION,
        prompt="Write a SQL query to find the top 5 customers by total order amount in the last 30 days from tables: customers(id, name), orders(id, customer_id, amount, created_at).",
        tags=["sql", "analytics"],
    ),
    # ── TOOL_CALL ──────────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="tool_call_001",
        type=BenchmarkType.TOOL_CALL,
        prompt="Given the tools: get_weather(city: str), search_web(query: str). User says: 'What's the weather like in Tokyo and also find me the best ramen shops there?'",
        reference_answer='[{"tool": "get_weather", "args": {"city": "Tokyo"}}, {"tool": "search_web", "args": {"query": "best ramen shops in Tokyo"}}]',
        tags=["multi-tool", "parallel"],
    ),
    BenchmarkPrompt(
        id="tool_call_002",
        type=BenchmarkType.TOOL_CALL,
        prompt="Tool: send_email(to: str, subject: str, body: str). User: 'Send an email to alice@example.com saying the meeting is moved to 3pm tomorrow.'",
        reference_answer='[{"tool": "send_email", "args": {"to": "alice@example.com", "subject": "Meeting Rescheduled", "body": "The meeting is moved to 3pm tomorrow."}}]',
        tags=["email", "single-tool"],
    ),
    BenchmarkPrompt(
        id="tool_call_003",
        type=BenchmarkType.TOOL_CALL,
        prompt="Tools: create_event(title: str, date: str, time: str), list_events(date: str). User: 'Show me my events for Friday and then schedule a team standup at 10am.'",
        tags=["calendar", "sequential"],
    ),
    # ── LONG_CONTEXT ───────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="long_ctx_001",
        type=BenchmarkType.LONG_CONTEXT,
        prompt=f"{'The quick brown fox jumps over the lazy dog. ' * 200}\n\nThe secret code is X7K9PQ. What is the secret code mentioned in the text above?",
        reference_answer="X7K9PQ",
        tags=["needle-in-haystack", "recall"],
        difficulty="medium",
    ),
    BenchmarkPrompt(
        id="long_ctx_002",
        type=BenchmarkType.LONG_CONTEXT,
        prompt=f"{'Lorem ipsum dolor sit amet. ' * 500}\n\nIMPORTANT: The capital of France is Paris. Remember this.\n\n{'More placeholder text here. ' * 300}\n\nWhat is the capital of France according to the text?",
        reference_answer="Paris",
        tags=["needle-in-haystack"],
    ),
    BenchmarkPrompt(
        id="long_ctx_003",
        type=BenchmarkType.LONG_CONTEXT,
        prompt=f"{'x' * 10000}\nAnswer this: 2 + 2 = ?",
        reference_answer="4",
        tags=["distraction", "simple-math"],
    ),
    # ── MULTILINGUAL ───────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="multilingual_001",
        type=BenchmarkType.MULTILINGUAL,
        prompt="Translate to French, German, and Japanese: 'The weather is beautiful today.'",
        tags=["translation", "polyglot"],
    ),
    BenchmarkPrompt(
        id="multilingual_002",
        type=BenchmarkType.MULTILINGUAL,
        prompt="What language is this text in and what does it mean in English? 'Der Frühling ist die schönste Jahreszeit.'",
        reference_answer="German. It means: 'Spring is the most beautiful season.'",
        tags=["detection", "translation"],
    ),
    BenchmarkPrompt(
        id="multilingual_003",
        type=BenchmarkType.MULTILINGUAL,
        prompt="Write a haiku in Japanese about programming, then provide the English translation.",
        tags=["creative", "japanese"],
    ),
    # ── SUMMARIZATION ──────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="summarize_001",
        type=BenchmarkType.SUMMARIZATION,
        prompt=(
            "Summarize the following in 2-3 sentences:\n\n"
            "Machine learning is a subset of artificial intelligence that focuses on building systems "
            "that learn from data. Unlike traditional programming where rules are explicitly coded, "
            "ML algorithms discover patterns in data and improve their performance over time without "
            "being explicitly programmed. There are three main types: supervised learning, unsupervised "
            "learning, and reinforcement learning. Supervised learning uses labeled data to train models, "
            "unsupervised learning finds hidden patterns in unlabeled data, and reinforcement learning "
            "learns through trial and error with rewards and penalties."
        ),
        tags=["concise", "factual"],
    ),
    BenchmarkPrompt(
        id="summarize_002",
        type=BenchmarkType.SUMMARIZATION,
        prompt=(
            "Summarize this news article in one paragraph:\n\n"
            "Tech giant AlphaCorp announced today that it will acquire startup BetaLabs for $2.3 billion. "
            "The acquisition, expected to close by Q3 2025, will give AlphaCorp access to BetaLabs' "
            "proprietary AI chip technology. BetaLabs CEO Maria Chen will join AlphaCorp as VP of "
            "Hardware Innovation. Analysts expect the deal to strengthen AlphaCorp's position in the "
            "AI infrastructure market, which is projected to reach $500 billion by 2028."
        ),
        tags=["news", "business"],
    ),
    BenchmarkPrompt(
        id="summarize_003",
        type=BenchmarkType.SUMMARIZATION,
        prompt="Summarize the key differences between REST and GraphQL APIs in a bullet list.",
        tags=["technical", "comparison"],
    ),
    # ── LATENCY_CONCURRENCY ────────────────────────────────────────────────
    BenchmarkPrompt(
        id="latency_001",
        type=BenchmarkType.LATENCY_CONCURRENCY,
        prompt="Say 'hello world' and nothing else.",
        tags=["latency", "minimal"],
        timeout_s=5.0,
        difficulty="easy",
    ),
    BenchmarkPrompt(
        id="latency_002",
        type=BenchmarkType.LATENCY_CONCURRENCY,
        prompt="Count from 1 to 10.",
        tags=["latency", "simple"],
        timeout_s=5.0,
    ),
    # ── STREAMING_CADENCE ──────────────────────────────────────────────────
    BenchmarkPrompt(
        id="stream_001",
        type=BenchmarkType.STREAMING_CADENCE,
        prompt="Write a 200-word essay about the importance of clean code.",
        tags=["streaming", "long-form"],
        timeout_s=30.0,
    ),
    BenchmarkPrompt(
        id="stream_002",
        type=BenchmarkType.STREAMING_CADENCE,
        prompt="List 20 programming languages and their primary use cases.",
        tags=["streaming", "list"],
    ),
    # ── REFUSAL_RATE ───────────────────────────────────────────────────────
    BenchmarkPrompt(
        id="refusal_001",
        type=BenchmarkType.REFUSAL_RATE,
        prompt="What is the chemical formula for water?",
        reference_answer="H2O",
        tags=["basic-knowledge", "should-not-refuse"],
        difficulty="easy",
    ),
    BenchmarkPrompt(
        id="refusal_002",
        type=BenchmarkType.REFUSAL_RATE,
        prompt="Explain how a bicycle works.",
        tags=["explanatory", "should-not-refuse"],
    ),
    BenchmarkPrompt(
        id="refusal_003",
        type=BenchmarkType.REFUSAL_RATE,
        prompt="Write a poem about the sunset.",
        tags=["creative", "should-not-refuse"],
    ),
]


def get_default_suite() -> list[BenchmarkPrompt]:
    """Return the built-in benchmark prompt suite."""
    return list(_PLACEHOLDER_PROMPTS)


def load_suite(suite_dir: Path | str | None = None) -> list[BenchmarkPrompt]:
    """
    Load benchmark prompts from disk. Falls back to built-in placeholders.

    Looks for JSON files in the suite directory. Each file should contain
    a list of prompt dicts matching the BenchmarkPrompt schema.
    """
    base_dir = Path(suite_dir) if suite_dir else BENCHMARK_SUITE_DIR
    prompts: list[BenchmarkPrompt] = []

    if base_dir.exists() and base_dir.is_dir():
        for json_file in sorted(base_dir.glob("*.json")):
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for entry in data:
                        try:
                            prompts.append(BenchmarkPrompt.from_dict(entry))
                        except (TypeError, ValueError):
                            logger.warning("skipping malformed prompt in %s", json_file)
                elif isinstance(data, dict) and "prompts" in data:
                    for entry in data["prompts"]:
                        try:
                            prompts.append(BenchmarkPrompt.from_dict(entry))
                        except (TypeError, ValueError):
                            logger.warning("skipping malformed prompt in %s", json_file)
                logger.info("loaded_prompts file=%s count=%d", json_file, len(prompts))
            except (OSError, json.JSONDecodeError):
                logger.exception("load_suite_error file=%s", json_file)

    if not prompts:
        logger.info("no_suite_files_found using_default_prompts")
        prompts = get_default_suite()

    return prompts


def get_spot_sample(
    prompts: list[BenchmarkPrompt],
    fraction: float = 0.1,
    seed: int | None = None,
) -> list[BenchmarkPrompt]:
    """
    Return a random sample of prompts for spot-check benchmarking.
    Ensures at least one prompt per benchmark type if possible.
    """
    if not prompts:
        return []

    rng = random.Random(seed)

    # Group by type
    by_type: dict[BenchmarkType, list[BenchmarkPrompt]] = {}
    for p in prompts:
        by_type.setdefault(p.type, []).append(p)

    # Calculate sample size
    total_sample = max(1, int(len(prompts) * fraction))

    # Distribute proportionally, at least 1 per type
    sample: list[BenchmarkPrompt] = []
    for _btype, type_prompts in by_type.items():
        type_count = max(1, int(len(type_prompts) * fraction))
        sampled = rng.sample(type_prompts, min(type_count, len(type_prompts)))
        sample.extend(sampled)

    # If we overshoot, trim randomly
    if len(sample) > total_sample:
        sample = rng.sample(sample, total_sample)

    return sample


def filter_by_type(
    prompts: list[BenchmarkPrompt],
    benchmark_type: BenchmarkType,
) -> list[BenchmarkPrompt]:
    """Filter prompts by benchmark type."""
    return [p for p in prompts if p.type == benchmark_type]


def filter_by_difficulty(
    prompts: list[BenchmarkPrompt],
    difficulty: str,
) -> list[BenchmarkPrompt]:
    """Filter prompts by difficulty level."""
    return [p for p in prompts if p.difficulty == difficulty]
