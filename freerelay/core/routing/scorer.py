"""
FreeRelay — Expected Utility Scorer (§14.1)
============================================
Routes on utility = P(success) × quality × schema × latency × cost × safety.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from freerelay.core.intelligence.profiler import WorkloadProfile
from freerelay.core.models.capability import CapabilityMatrix, ModelCapability
from freerelay.core.resilience.budget import BudgetForecaster
from freerelay.core.resilience.circuit_breaker import CircuitBreaker
from freerelay.core.routing.policy import RoutingDirective

if TYPE_CHECKING:
    from freerelay.core.routing.engine import ProviderSlot


def _capability_score(
    provider_name: str,
    task_family: str,
    capability_matrix: CapabilityMatrix | None,
) -> float:
    if capability_matrix is None:
        return 0.8

    provider_models = capability_matrix.get_provider_models(provider_name)
    if not provider_models:
        return 0.3

    best = 0.0
    for model in provider_models.values():
        if task_family in model.strengths:
            best = max(best, 0.95)
        elif task_family not in model.weaknesses:
            best = max(best, 0.7)
        else:
            best = max(best, 0.4)
    return best if best > 0 else 0.4


def compute_capability_score(
    provider_name: str,
    task_family: str,
    capability_matrix: CapabilityMatrix | None,
) -> float:
    return _capability_score(provider_name, task_family, capability_matrix)


def _quality_score(models: Iterable[ModelCapability]) -> float:
    tier_map = {"low": 0.6, "medium": 0.8, "high": 1.0}
    values = []
    for model in models:
        values.append(tier_map.get(model.quality_tier, 0.75))
    if not values:
        return 0.7
    return sum(values) / len(values)


def _schema_success_prob(
    models: Iterable[ModelCapability],
    directive: RoutingDirective | None,
) -> float:
    supports_json = any(getattr(model, "supports_json_mode", False) for model in models)
    base = 0.92 if supports_json else 0.78
    if directive and directive.enforce_mode == "json":
        base = min(1.0, base + 0.05)
    return base


def _latency_score(latency_p95_ms: float) -> float:
    if latency_p95_ms <= 0:
        return 1.0
    return 1.0 / (1.0 + latency_p95_ms / 1000.0)


def compute_latency_score(latency_p95_ms: float) -> float:
    return _latency_score(latency_p95_ms)


def _safety_multiplier(
    profile: WorkloadProfile,
    models: Iterable[ModelCapability],
) -> float:
    if profile.safety_posture == "locked_down":
        if any(getattr(model, "supports_json_mode", False) for model in models):
            return 1.0
        return 0.85
    return 1.0


def compute_expected_utility(
    slot: ProviderSlot,
    profile: WorkloadProfile,
    capability_matrix: CapabilityMatrix | None,
    budget: BudgetForecaster,
    directive: RoutingDirective | None,
) -> float:
    capability = _capability_score(
        slot.provider.name, profile.task_family, capability_matrix
    )
    success_prob = max(0.1, (capability + slot.circuit.get_score()) / 2.0)
    provider_models = (
        list(capability_matrix.get_provider_models(slot.provider.name).values())
        if capability_matrix
        else []
    )
    quality = _quality_score(provider_models)
    schema = _schema_success_prob(provider_models, directive)
    latency = _latency_score(slot.latency_p95_ms)
    cost = budget.get_budget_score(slot.provider.name)
    safety = _safety_multiplier(profile, provider_models)
    policy_weight = directive.policy_weight if directive else 1.0

    return success_prob * quality * schema * latency * cost * safety * policy_weight


def compute_composite_score(
    provider_name: str,
    task_family: str,
    circuit_breaker: CircuitBreaker,
    budget: BudgetForecaster,
    latency_p95_ms: float,
    capability_matrix: CapabilityMatrix | None = None,
) -> float:
    capability = compute_capability_score(provider_name, task_family, capability_matrix)
    circuit = circuit_breaker.get_score()
    if circuit == 0.0:
        return 0.0
    budget_score = budget.get_budget_score(provider_name)
    latency = compute_latency_score(latency_p95_ms)
    return capability * circuit * budget_score * latency
