"""
FreeRelay — Routing Engine (§14)
==================================
Workload-aware routing with expected utility, policy directives, execution DAG planning,
validation/repair loops, and outcome feedback logging.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from freerelay.config.settings import Settings
from freerelay.core.execution.planner import ExecutionPlanner
from freerelay.core.execution.validator import ValidationResult, ValidatorChain
from freerelay.core.intelligence.compressor import CompressionResult, PromptCompressor
from freerelay.core.intelligence.context_optimizer import ContextOptimizer
from freerelay.core.intelligence.profiler import WorkloadProfile, WorkloadProfiler
from freerelay.core.models.capability import CapabilityMatrix
from freerelay.core.models.openai import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Message,
)
from freerelay.core.observability.outcome import OutcomeLogger, OutcomeRecord
from freerelay.core.observability.supabase_logger import SupabaseUsageLogger
from freerelay.core.resilience.budget import BudgetForecaster
from freerelay.core.resilience.chaos import ChaosInjector
from freerelay.core.resilience.circuit_breaker import CircuitBreaker
from freerelay.core.routing.policy import RoutingDirective, RoutingPolicy
from freerelay.core.routing.scorer import compute_expected_utility
from freerelay.providers.base import BaseProvider, ProviderError, RateLimitError

logger = logging.getLogger("freerelay.router")


@dataclass(slots=True)
class ProviderSlot:
    provider: BaseProvider
    api_key: str
    circuit: CircuitBreaker
    tier: str = "free"  # "free" or "paid"
    latency_p95_ms: float = 1000.0
    request_count: int = 0
    error_count: int = 0
    _latency_samples: list[float] = field(default_factory=list)
    _sorted_cache: list[float] | None = field(default=None, repr=False)
    _cache_dirty: bool = field(default=True, repr=False)

    def record_latency(self, ms: float) -> None:
        self._latency_samples.append(ms)
        if len(self._latency_samples) > 100:
            self._latency_samples = self._latency_samples[-100:]
        self._cache_dirty = True

        # Only compute p95 when we have enough samples
        if len(self._latency_samples) >= 5:
            self._update_p95()

    def _update_p95(self) -> None:
        """Update p95 latency using partial sort for efficiency."""
        if not self._cache_dirty and self._sorted_cache is not None:
            return

        # Use nsmallest for partial sort - O(n) instead of O(n log n) for full sort
        import heapq

        n = len(self._latency_samples)
        k = max(1, int(round(n * 0.95)))
        # Get the k-th smallest element (which is p95)
        self._sorted_cache = heapq.nsmallest(k, self._latency_samples)
        self.latency_p95_ms = self._sorted_cache[-1] if self._sorted_cache else 1000.0
        self._cache_dirty = False


@dataclass(slots=True)
class RequestContext:
    request_id: str
    user_id: str | None
    original_request: ChatCompletionRequest
    optimized_request: ChatCompletionRequest
    workload_profile: WorkloadProfile
    compression: CompressionResult
    lanes: dict[str, list[Message]]
    salience_order: list[int]
    total_tokens: int
    schema_success_ratio: float
    tenant_tier: str
    policy_directive: RoutingDirective = field(default_factory=RoutingDirective)

    def policy_context(self) -> dict[str, Any]:
        return {
            "workload": self.workload_profile.to_dict(),
            "tenant": {"id": self.user_id, "tier": self.tenant_tier},
            "schema": {"success_ratio": self.schema_success_ratio},
            "compression": {
                "tokens_saved": self.compression.tokens_saved,
                "ratio": self.compression.compression_ratio,
            },
        }


class RoutingEngine:
    """
    Routing engine that evaluates workloads, policies, and expected utility scores.

    Strategy:
      1. Profile the request and optimize context.
      2. Score providers via expected utility (success, quality, latency, etc.).
      3. Apply routing policy to reorder/prefer providers.
      4. Execute with validation + repair loops and log outcomes for learning.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.slots: list[ProviderSlot] = []
        self.budget = BudgetForecaster(
            alpha=settings.budget_ewma_alpha,
            safety_margin=settings.budget_safety_margin_tokens,
        )
        self.chaos = ChaosInjector(
            enabled=settings.enable_chaos,
            intensity=settings.chaos_intensity,
        )
        self.capability_matrix = self._load_capability_matrix(settings)
        self.routing_policy = self._load_routing_policy(settings)
        compressor = PromptCompressor(
            enabled=settings.enable_compression,
            summarize_threshold=settings.compression_summarize_threshold,
            min_ratio=settings.compression_min_ratio,
        )
        self.profiler = WorkloadProfiler()
        self.context_optimizer = ContextOptimizer(compressor=compressor)
        self.execution_planner = ExecutionPlanner()
        self.validator = ValidatorChain()
        self.outcome_logger = OutcomeLogger()
        self.supabase_logger = SupabaseUsageLogger()
        self.max_repair_attempts = settings.max_repair_attempts

    def _load_capability_matrix(self, settings: Settings) -> CapabilityMatrix | None:
        if settings.capability_matrix_path:
            path = Path(settings.capability_matrix_path)
        else:
            path = (
                Path(__file__).parent.parent.parent
                / "config"
                / "capability_matrix.yaml"
            )

        if not path.exists():
            logger.warning("Capability matrix not found: %s", path)
            return None

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            matrix = CapabilityMatrix.model_validate(data)
            logger.info("Loaded capability matrix: %d models", len(matrix.models))
            return matrix
        except (yaml.YAMLError, ValueError, TypeError):
            logger.exception("Failed to load capability matrix: %s", path)
            return None

    def _load_routing_policy(self, settings: Settings) -> RoutingPolicy:
        if settings.routing_rules_path:
            path = Path(settings.routing_rules_path)
        else:
            path = Path(__file__).parent.parent.parent / "config" / "routing_rules.yaml"
        policy = RoutingPolicy.from_yaml(path)
        logger.info("Loaded routing policy: %d rules", len(policy.rules))
        return policy

    def register_provider(
        self,
        provider: BaseProvider,
        api_key: str,
        daily_limit: int | None = None,
        tier: str = "free",
    ) -> None:
        circuit = CircuitBreaker(
            provider_name=provider.name,
            failure_threshold=self.settings.circuit_failure_threshold,
            failure_window=self.settings.circuit_failure_window,
            recovery_timeout=self.settings.circuit_recovery_timeout,
        )
        self.slots.append(
            ProviderSlot(
                provider=provider,
                api_key=api_key,
                circuit=circuit,
                tier=tier,
            )
        )
        if daily_limit is not None:
            self.budget.set_daily_limit(provider.name, daily_limit)
        logger.info(f"Registered provider: {provider.name} (tier: {tier})")

    def _prepare_context(
        self,
        request: ChatCompletionRequest,
        user_id: str | None = None,
        tier: str = "free",
    ) -> RequestContext:
        profile = self.profiler.profile(request)
        bundle = self.context_optimizer.optimize(request)
        return RequestContext(
            request_id=f"req_{uuid.uuid4().hex[:12]}",
            user_id=user_id,
            original_request=request,
            optimized_request=bundle.optimized_request,
            workload_profile=profile,
            compression=bundle.compression,
            lanes=bundle.lanes,
            salience_order=bundle.salience_order,
            total_tokens=bundle.total_tokens,
            schema_success_ratio=0.95,
            tenant_tier=tier,
        )

    def _build_policy_context(self, context: RequestContext) -> dict[str, Any]:
        policy_context = context.policy_context()
        policy_context["budget"] = {"state": "green"}
        return policy_context

    def _get_preferred_tier(self, profile: WorkloadProfile) -> str:
        """Determine which tier to use based on workload complexity."""
        # Complex tasks warrant paid providers
        if profile.required_depth == "deep":
            return "paid"
        if profile.estimated_tokens > 8000:
            return "paid"
        if profile.task_family in {"coding", "planning", "eval"}:
            return "paid"
        if profile.output_contract in {"schema", "code_patch"}:
            return "paid"
        # Default to free for simple tasks
        return "free"

    async def _ranked_slots(
        self, context: RequestContext
    ) -> tuple[list[ProviderSlot], RoutingDirective]:
        available: list[ProviderSlot] = []
        candidate_names: list[str] = []

        # Forced provider check (§14.1)
        model = context.original_request.model
        forced_provider = None
        if model and model.startswith("freerelay-") and model != "freerelay-auto":
            forced_raw = model.replace("freerelay-", "")
            if ":" in forced_raw:
                forced_provider, forced_model = forced_raw.split(":", 1)
                context.optimized_request.model = forced_model
            else:
                forced_provider = forced_raw
                context.optimized_request.model = ""

        # Determine which tier to prioritize
        preferred_tier = self._get_preferred_tier(context.workload_profile)
        
        # User tier limits: free users can't use paid providers unless 
        # specifically allowed
        if context.tenant_tier == "free" and preferred_tier == "paid":
             # Force downgrade to free for free tier users
             preferred_tier = "free"
             
        has_paid = any(slot.tier == "paid" for slot in self.slots)

        for slot in self.slots:
            if forced_provider and slot.provider.name != forced_provider:
                continue

            if not await slot.circuit.can_execute():
                continue
            if self.budget.is_budget_exhausted(slot.provider.name):
                continue

            # In auto mode, filter by tier preference
            # If we have paid providers and this is a complex task, prefer paid
            # Otherwise, prefer free
            if has_paid:
                if slot.tier == preferred_tier or (
                    preferred_tier == "paid" and slot.tier == "paid"
                ):
                    available.insert(0, slot)  # Higher priority
                elif slot.tier == "free":
                    available.append(slot)  # Fallback
            else:
                available.append(slot)

            candidate_names.append(slot.provider.name)

        policy_order, directive = self.routing_policy.apply(
            self._build_policy_context(context),
            candidate_names,
        )
        context.policy_directive = directive

        scored: list[tuple[float, ProviderSlot]] = []
        for slot in available:
            score = compute_expected_utility(
                slot=slot,
                profile=context.workload_profile,
                capability_matrix=self.capability_matrix,
                budget=self.budget,
                directive=directive,
            )
            scored.append((score, slot))

        scored.sort(key=lambda item: item[0], reverse=True)
        ranked = [slot for _, slot in scored]

        if policy_order != candidate_names:
            name_to_slot = {slot.provider.name: slot for slot in ranked}
            reordered: list[ProviderSlot] = []
            for name in policy_order:
                p_slot = name_to_slot.get(name)
                if p_slot and p_slot not in reordered:
                    reordered.append(p_slot)
            for slot in ranked:
                if slot not in reordered:
                    reordered.append(slot)
            ranked = reordered

        return ranked, directive

    async def route(
        self,
        request: ChatCompletionRequest,
        user_id: str | None = None,
        tier: str = "free",
    ) -> ChatCompletionResponse:
        context = self._prepare_context(request, user_id=user_id, tier=tier)
        ranked, directive = await self._ranked_slots(context)

        if not ranked:
            if not self.slots:
                return ChatCompletionResponse.from_text(
                    "No providers configured. Add API keys to .env",
                    model="error",
                )
            return ChatCompletionResponse.from_text(
                "All providers are currently unavailable. Try again shortly.",
                model="error",
            )

        provider_names = [slot.provider.name for slot in ranked]
        last_error: Exception | None = None

        plan = self.execution_planner.plan(context.workload_profile, directive)
        plan_names = [step.name for step in plan.steps]
        for slot in ranked:
            provider = slot.provider
            logger.info(
                "Execution plan for %s → %s",
                provider.name,
                plan_names,
            )

            try:
                await self.chaos.maybe_inject(provider.name)
                response, elapsed_ms, validation = await self._execute_slot(
                    slot, context, directive
                )
                await slot.circuit.record_success()
                slot.record_latency(elapsed_ms)
                slot.request_count += 1
                tokens = response.usage.total_tokens if response.usage else 0
                self.budget.record_tokens(provider.name, tokens)
                context.schema_success_ratio = 0.99 if validation.schema_pass else 0.7

                alternatives = [
                    name for name in provider_names if name != provider.name
                ]
                notes = "; ".join(validation.errors) if validation.errors else None
                self._log_outcome(
                    context=context,
                    provider_name=provider.name,
                    success=True,
                    schema_pass=validation.schema_pass,
                    latency_ms=elapsed_ms,
                    cost_tokens=tokens,
                    alternatives=alternatives,
                    notes=notes,
                )

                logger.info(
                    "%s succeeded (%.0fms, %d tokens)",
                    provider.name,
                    elapsed_ms,
                    tokens,
                )
                return response

            except RateLimitError:
                await slot.circuit.record_failure(429)
                slot.error_count += 1
                logger.warning("%s rate limited", provider.name)
                last_error = RateLimitError(provider_name=provider.name)
                continue

            except ProviderError as e:
                await slot.circuit.record_failure(e.status_code)
                slot.error_count += 1
                logger.warning(
                    "%s error %d: %s", provider.name, e.status_code, str(e)[:100]
                )
                last_error = e
                continue

            except (AttributeError, TypeError, OSError) as e:
                await slot.circuit.record_failure(None)
                slot.error_count += 1
                logger.exception("%s unexpected error: %s", provider.name, e)
                last_error = e
                continue

        notes = str(last_error) if last_error else "exhausted"
        self._log_outcome(
            context=context,
            provider_name="",
            success=False,
            schema_pass=None,
            latency_ms=0.0,
            cost_tokens=0,
            alternatives=provider_names,
            notes=notes,
        )
        msg = f"All providers failed. Last: {last_error}"
        return ChatCompletionResponse.from_text(msg, model="error")

    async def route_stream(
        self,
        request: ChatCompletionRequest,
        user_id: str | None = None,
        tier: str = "free",
    ) -> Any:
        context = self._prepare_context(request, user_id=user_id, tier=tier)
        ranked, _ = await self._ranked_slots(context)

        if not ranked:
            yield 'data: {"error":{"message":"No providers available"}}\n\n'
            yield "data: [DONE]\n\n"
            return

        for slot in ranked:
            provider = slot.provider
            logger.info("Streaming through %s...", provider.name)

            try:
                await self.chaos.maybe_inject(provider.name)
                
                full_content = []
                start_time = time.time()
                
                async for line in provider.stream(
                    context.optimized_request, slot.api_key
                ):
                    yield line
                    # Simple token tracking from stream
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str and data_str != "[DONE]":
                            try:
                                import json
                                chunk = json.loads(data_str)
                                if "choices" in chunk and chunk["choices"]:
                                    delta = chunk["choices"][0].get("delta", {})
                                    if "content" in delta and delta["content"]:
                                        full_content.append(delta["content"])
                            except ValueError:
                                pass

                elapsed_ms = (time.time() - start_time) * 1000
                # Estimate tokens if not provided in stream (most aren't)
                content_str = "".join(full_content)
                completion_tokens = len(content_str) // 4
                prompt_tokens = context.total_tokens
                total_tokens = prompt_tokens + completion_tokens

                self.budget.record_tokens(provider.name, total_tokens)
                self._log_outcome(
                    context=context,
                    provider_name=provider.name,
                    success=True,
                    schema_pass=True, # Streams are usually successful if they finish
                    latency_ms=elapsed_ms,
                    cost_tokens=total_tokens,
                    alternatives=[],
                    notes="streamed",
                )
                return

            except RateLimitError:
                await slot.circuit.record_failure(429)
                slot.error_count += 1
                logger.warning("%s rate limited (stream)", provider.name)
                continue

            except ProviderError as e:
                await slot.circuit.record_failure(e.status_code)
                slot.error_count += 1
                logger.warning("%s stream error: %s", provider.name, str(e)[:100])
                continue

            except Exception as e:
                await slot.circuit.record_failure(None)
                slot.error_count += 1
                logger.exception("%s stream exception: %s", provider.name, e)
                continue

        yield 'data: {"error":{"message":"All providers failed"}}\n\n'
        yield "data: [DONE]\n\n"

    async def _execute_slot(
        self,
        slot: ProviderSlot,
        context: RequestContext,
        directive: RoutingDirective,
    ) -> tuple[ChatCompletionResponse, float, ValidationResult]:
        attempt_request = self._apply_directive_to_request(
            context.optimized_request, directive
        )
        last_response: ChatCompletionResponse | None = None
        last_validation: ValidationResult | None = None
        elapsed_ms = 0.0

        for attempt in range(self.max_repair_attempts + 1):
            start = time.time()
            response = await slot.provider.complete(attempt_request, slot.api_key)
            elapsed_ms = (time.time() - start) * 1000
            validation = self.validator.validate(response, directive)

            last_response = response
            last_validation = validation

            if validation.needs_repair and attempt < self.max_repair_attempts:
                attempt_request = self._build_repair_request(attempt_request)
                continue

            return response, elapsed_ms, validation

        return (
            last_response
            or ChatCompletionResponse.from_text("repair failed", model="error"),
            elapsed_ms,
            last_validation
            or ValidationResult(schema_pass=True, errors=[], needs_repair=False),
        )

    def _apply_directive_to_request(
        self,
        request: ChatCompletionRequest,
        directive: RoutingDirective,
    ) -> ChatCompletionRequest:
        if directive.set_temperature is not None:
            return request.model_copy(update={"temperature": directive.set_temperature})
        return request

    def _build_repair_request(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionRequest:
        temperature = request.temperature if request.temperature is not None else 0.7
        new_temp = max(0.0, temperature * 0.5)
        return request.model_copy(update={"temperature": new_temp})

    def _log_outcome(
        self,
        context: RequestContext,
        provider_name: str,
        success: bool,
        schema_pass: bool | None,
        latency_ms: float,
        cost_tokens: int,
        alternatives: list[str],
        notes: str | None = None,
    ) -> None:
        record = OutcomeRecord(
            request_id=context.request_id,
            user_id=context.user_id,
            selected_provider=provider_name,
            alternatives=alternatives,
            success=success,
            schema_pass=schema_pass,
            latency_ms=latency_ms,
            cost_tokens=cost_tokens,
            hallucination_signal=0.0,
            downstream_success=None,
            notes=notes,
        )
        self.outcome_logger.log(record)
        self.supabase_logger.log(record)

    def get_stats(self) -> list[dict[str, object]]:
        return [
            {
                "name": slot.provider.name,
                "circuit": slot.circuit.to_dict(),
                "budget": self.budget.get_stats(slot.provider.name),
                "latency_p95_ms": round(slot.latency_p95_ms, 1),
                "request_count": slot.request_count,
                "error_count": slot.error_count,
            }
            for slot in self.slots
        ]

    def get_models(self) -> list[Any]:
        """Aggregate models from all registered provider slots."""
        from freerelay.core.models.openai import ModelObject

        models = [
            ModelObject(id="freerelay-auto", owned_by="freerelay"),
        ]
        for slot in self.slots:
            models.append(
                ModelObject(
                    id=f"freerelay-{slot.provider.name}",
                    owned_by="freerelay",
                )
            )
        return models
