"""
FreeRelay Data Plane — Expected Utility Scorer (§5.1)
========================================================
Computes expected utility for provider selection.

All 10 terms from spec §5.1:
  p_success, quality, schema_prob, latency_utility, cost_utility,
  safety_utility, tenant_weight, circuit_score, budget_score, ucb_bonus

Economic policy modulation:
  cheapest: (cost=0.4, quality=1.6)
  balanced: (cost=1.0, quality=1.0)
  best:     (cost=1.6, quality=0.4)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freerelay.data_plane.profiler.workload import WorkloadProfile
    from freerelay.data_plane.routing.engine import ModelSlot

# Economic policy weights: (cost_exponent, quality_exponent)
_ECONOMIC_WEIGHTS: dict[str, tuple[float, float]] = {
    "cheapest": (0.4, 1.6),
    "balanced": (1.0, 1.0),
    "best": (1.6, 0.4),
}

# UCB1 exploration constant
_UCB_C = 1.414  # sqrt(2)


def _p_success(slot: ModelSlot, profile: WorkloadProfile) -> float:
    """Probability of successful completion."""
    base = 0.85

    # Circuit breaker adjustment
    base *= slot.circuit_score

    # Tool support check
    if profile.tool_dependence == "mandatory" and not slot.supports_tools:
        return 0.05

    # JSON mode check
    if profile.output_contract in ("json", "schema") and not slot.supports_json_mode:
        base *= 0.7

    return max(0.01, min(1.0, base))


def _quality(slot: ModelSlot, profile: WorkloadProfile) -> float:
    """Quality score based on tier and task alignment."""
    tier_map = {"low": 0.5, "medium": 0.75, "high": 1.0}
    base = tier_map.get(slot.quality_tier, 0.7)

    # Boost for high-precision tasks on high-quality models
    if profile.precision_sensitivity == "high" and slot.quality_tier == "high":
        base = min(1.0, base + 0.15)

    # Penalize low-quality for deep analysis
    if profile.required_depth == "deep" and slot.quality_tier == "low":
        base *= 0.6

    return base


def _schema_prob(slot: ModelSlot, profile: WorkloadProfile) -> float:
    """Probability of schema/format compliance."""
    if profile.output_contract in ("json", "schema"):
        return slot.schema_compliance_rate
    if profile.output_contract == "tool_calls":
        return slot.schema_compliance_rate if slot.supports_tools else 0.3
    return 0.95  # Prose doesn't need schema compliance


def _latency_score(latency_p95_ms: float) -> float:
    if latency_p95_ms <= 0:
        return 1.0
    return 1.0 / (1.0 + latency_p95_ms / 1000.0)


def _latency_utility(slot: ModelSlot, profile: WorkloadProfile) -> float:
    """Utility based on latency expectations."""
    if profile.latency_class == "interactive":
        # Strong preference for fast models
        return 1.0 / (1.0 + slot.latency_p95_ms / 500.0)
    if profile.latency_class == "async":
        return 1.0 / (1.0 + slot.latency_p95_ms / 2000.0)
    # batch — latency matters less
    return 1.0 / (1.0 + slot.latency_p95_ms / 10000.0)


def _cost_utility(slot: ModelSlot) -> float:
    """Utility based on cost (lower cost = higher utility)."""
    if slot.cost_per_1k_tokens <= 0:
        return 1.0  # Free tier
    # Log-scaled: 0.001 → 0.9, 0.01 → 0.6, 0.1 → 0.3
    return max(0.1, 1.0 - math.log10(slot.cost_per_1k_tokens + 0.0001) / 4.0)


def _safety_utility(slot: ModelSlot, profile: WorkloadProfile) -> float:
    """Safety utility based on posture requirements."""
    if profile.safety_posture == "locked_down":
        # Prefer models with JSON mode for structured, safe outputs
        return 0.9 if slot.supports_json_mode else 0.7
    if profile.safety_posture == "permissive":
        return 1.0
    return 0.9  # standard


def _tenant_weight(profile: WorkloadProfile) -> float:
    """Tenant-level weight from profile."""
    return 1.0  # Default; extended by tenant policy


def _circuit_score(slot: ModelSlot) -> float:
    """Circuit breaker health score."""
    return max(0.0, min(1.0, slot.circuit_score))


def _budget_score(slot: ModelSlot) -> float:
    """Budget availability score (assumed healthy without external state)."""
    return 1.0  # Extended by BudgetForecaster integration


def _ucb_bonus(
    slot: ModelSlot,
    total_pulls: int = 100,
    slot_pulls: int = 10,
) -> float:
    """
    UCB1 exploration bonus.

    Encourages trying under-explored providers.
    """
    if slot_pulls <= 0:
        return _UCB_C * 2.0  # Max bonus for untried providers
    return _UCB_C * math.sqrt(math.log(max(1, total_pulls)) / slot_pulls)


def expected_utility(
    slot: ModelSlot,
    profile: WorkloadProfile,
    total_pulls: int = 100,
    slot_pulls: int = 10,
) -> tuple[float, dict[str, float]]:
    """
    Compute expected utility score per spec §5.1.

    EU = p_success × quality^q_exp × schema × latency × cost^c_exp
         × safety × tenant × circuit × budget × (1 + ucb_bonus)

    Args:
        slot: Provider/model slot to score.
        profile: Workload profile from the profiler.
        total_pulls: Total number of routing decisions made.
        slot_pulls: Number of times this slot has been selected.

    Returns:
        (score, breakdown) — score is float, breakdown is per-term dict.
    """
    policy = profile.economic_policy if profile else "balanced"
    cost_exp, quality_exp = _ECONOMIC_WEIGHTS.get(policy, (1.0, 1.0))

    p = _p_success(slot, profile)
    q = _quality(slot, profile) ** quality_exp
    s = _schema_prob(slot, profile)
    l = _latency_utility(slot, profile)
    c = _cost_utility(slot) ** cost_exp
    sa = _safety_utility(slot, profile)
    tw = _tenant_weight(profile)
    cs = _circuit_score(slot)
    bs = _budget_score(slot)
    ucb = _ucb_bonus(slot, total_pulls, slot_pulls)

    score = p * q * s * l * c * sa * tw * cs * bs * (1.0 + ucb)

    breakdown = {
        "p_success": round(p, 4),
        "quality": round(q, 4),
        "schema_prob": round(s, 4),
        "latency_utility": round(l, 4),
        "cost_utility": round(c, 4),
        "safety_utility": round(sa, 4),
        "tenant_weight": round(tw, 4),
        "circuit_score": round(cs, 4),
        "budget_score": round(bs, 4),
        "ucb_bonus": round(ucb, 4),
        "economic_policy": policy,
        "cost_exponent": cost_exp,
        "quality_exponent": quality_exp,
    }

    return score, breakdown
