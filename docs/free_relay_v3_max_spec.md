# FreeRelay v3 MAX Specification

This document distills the [FreeRelay_v3_MAX](../FreeRelay_v3_MAX.zip) engineering specification into a single reference that the repository can consume directly. The max spec defines a programmable inference **operating system** that profiles every request, routes on expected outcome utility, executes declarative DAGs with judges/validators, validates and repairs results, and continuously learns from every outcome.

## Vision

FreeRelay is not merely a gateway or proxy; it is an inference control plane that governs every decision before, during, and after a model call. The real moat is the feedback loop: outcome records, judges, and repair attempts feed learning so routing choices improve with every request.

FreeRelay v3 MAX aims for:

- **Workload understanding** on ten structured axes before touching a provider.
- **Outcome-aware routing** powered by expected utility, policy weights, and learned success probabilities.
- **Execution DAG orchestration** with classifiers, generators, validators, judges, tooling, and repair loops.
- **Validation, repair, and correctness guarantees** that make output quality transactional.
- **Control-plane operations, experimentation, and economics** that keep the OS safe, observable, and ready for tenants.

## Five Foundational Pillars

| Pillar | Benefit | Commodity Alternative |
| --- | --- | --- |
| Workload understanding | Profile depth, safety, tool needs, contracts, economics before routing | Single-label intent classification |
| Outcome-aware routing | Learn P(success|workload,provider,config) and route on expected utility | Static scoring + health checks |
| Multi-step orchestration | Declarative DAGs with validation, repairs, judges | One request → one provider |
| Correctness guarantees | Validators + repair loops + validators make outputs transactional | Hope the model got it right |
| Control-plane operations | Policy-as-code, tenants, experiments, observability | YAML config + unused dashboard |

## Architecture Overview

### Control Plane vs Data Plane

| Concern | Control Plane | Data Plane |
| --- | --- | --- |
| Process | Dedicated Python service (or k8s deployment) owning policies, benchmarks, experiments | FastAPI/Uvicorn workers: stateless, horizontal |
| Latency budget | Seconds to minutes (intelligence over speed) | <5ms overhead on hot path |
| State | Mutable policy/registry, bandits, experiments | No durable state except outcome stream |
| Communication | Publishes via Redis Pub/Sub (`freerelay:policy:v2`) | Subscribes to policy updates |
| Writes | Policy, capability registry, bandit weights, benchmarks, telemetry | Outcome stream, circuit breaker, budget Lua scripts |

> Control-plane writes are immutable for the data plane; data plane writes only to the outcome stream, circuit breaker/budget Lua scripts.

### Communication Contracts

- **Redis Streams**: Outcome records flow from data plane → control plane. Retention: 7 days; consumer group `control-plane-learner`.
- **Redis Pub/Sub**: Policy updates broadcast at `freerelay:policy:v2`. Data plane hot-reloads on every publish.
- **Redis Hash/Sorted Set**: Capability registry, circuit/bandit/budget metadata read-only for data plane. Control plane owns writes via Lua/atomic scripts.

### Key Redis Schema

| Key Pattern | Type | Owner | TTL | Contents |
| --- | --- | --- | --- | --- |
| `freerelay:policy:v2` | String (JSON) | Control plane | None | Full routing policy object (versioned) |
| `freerelay:circuit:{provider}` | Hash | Data plane (Lua) | None | `state`, `failure_count`, `open_since_ts`, etc. |
| `freerelay:budget:{provider}:{key_hash}` | Hash | Data plane (Lua) | 86400 | Token counters + EWMA |
| `freerelay:bandit:{provider}:{model}:{family}` | Hash | Control plane | None | Mean quality, pulls, last update |
| `freerelay:capability:{provider}:{model}` | Hash | Control plane | None | 14 capability dimensions |
| `freerelay:benchmark:results:{provider}:{model}:{suite}` | Sorted Set | Control plane | 30d | Score → timestamp |
| `freerelay:cache:lsh:{hash}` | String (JSON) | Data plane | 3600 | Cache metadata |
| `freerelay:cache:response:{hash}` | String (JSON) | Data plane | 3600 | Stored response |
| `freerelay:outcomes` | Stream | Data plane | 7d | Outcome records |
| `freerelay:agent:{run_id}` | Hash | Data plane | 86400 | Agent run state |
| `freerelay:ratelimit:{namespace}:{window}` | String | Data plane (Lua) | 60s | Sliding window counter |
| `freerelay:idempotency:{request_id}` | String (JSON) | Data plane | 300s | Idempotency cache |
| `freerelay:experiment:{experiment_id}` | Hash | Control plane | None | Experiment config + metrics |
| `freerelay:cp:leader` | String | Control plane | 30s | Leader election lock |

## Data Schemas

### `WorkloadProfile`

Workload profiles are immutable after creation and attached to OpenTelemetry spans.

Fields include:

- Core identity: `request_id`, `namespace`, `created_ts`.
- Ten axes: `task_family`, `required_depth`, `precision_sensitivity`, `latency_class`, `context_topology`, `tool_dependence`, `determinism_needs`, `safety_posture`, `output_contract`, `economic_policy`.
- Derived metrics: token estimates, message count, system prompt presence, languages, image flags, schema hints.
- Profiler metadata: confidence, duration, version.

### `RoutingDecision`

- `ProviderScore` captures per-candidate utilities (expected utility, quality, latency, cost, safety, circuit/budget scores, UCB bonus, disqualification status).
- `RoutingDecision` includes request/workload, winner, candidate list, confidence gap, policy version, workflow, hedge flag, decision latency.

### `OutcomeRecord`

High-fidelity outcome signal feeding the control plane:

- Run metadata: provider/model chosen, alternatives, policy version, workflow, timestamps.
- Execution stats: latencies, token counts, hedge details, streaming flag.
- Quality: validation results, schema/repair success, judge scores, hallucination flags.
- Context: compression ratio, cache hints.
- Agent/tool telemetry: run IDs, steps, tool calls.
- User proxies: retries/regenerations.

## Workload Profiler

Profiler goals: <5ms p99, no LLM/network calls. Axes computed via heuristics, logistic regression, or headers:

| Axis | Implementation | Notes |
| --- | --- | --- |
| `task_family` | 8-way logistic regression on TF-IDF (system prompt + initial user message) | Model retrained weekly; inference <1ms |
| `required_depth` | Heuristic tokens/keywords | >2000 tokens → deep; keywords classify shallow/medium |
| `precision_sensitivity` | Derived from `(task_family, output_contract)` | Override via `X-FreeRelay-Precision` |
| `latency_class` | Header/heuristic | `X-FreeRelay-Latency-Class` prioritized |
| `context_topology` | Heuristics on tokens, images, tool outputs, conversation shape | |
| `tool_dependence` | Direct from `tools` + `tool_choice` | |
| `determinism_needs` | Header + fields | `seed` → replayable; keywords for strict |
| `safety_posture` | Tenant policy lookup (cached 60s) | Default `standard` |
| `output_contract` | Response format detection + prompts | `json_schema` vs `code_patch` vs `tool_calls` |
| `economic_policy` | Tenant policy, override header | Default `balanced` |

Confidence score modulates routing. Low confidence (<0.5) disables UCB exploration and routes to safest historical provider.

Profiler ships with 120 labeled cases (`tests/profiler/labeled_requests.jsonl`); CI enforces ≥92% axis accuracy.

## Routing Engine & Expected Utility

Every provider-model candidate is scored via expected utility when:

- Circuit state is CLOSED or HALF_OPEN.
- Budget remains (>0) and tenant policy allows the provider.

Components:

1. `p_success`: from bandit arms (prior if <10 pulls).
2. `quality_estimate`: EWMA judge scores by `(provider, task_family)`.
3. `schema_success_prob`: capability registry per output contract.
4. `latency_utility`: `1 / (1 + p95_ttft / budget_ms)`.
5. `cost_utility`: normalized against tenant cost ceiling.
6. `safety_utility`: binary match vs tenant safety tier.
7. `tenant_policy_weight`: allowlist gate.
8. `circuit_score`: CLOSED/HALF_OPEN/OPEN weights.
9. `budget_score`: `sqrt(remaining_ratio)`.
10. `ucb_bonus`: exploration term scaled from bandit totals.

The router merges expected utility with routing rules/policy DSL, validation directives, hedge requirements, and optional workflows.

## Execution DAG & Capability Intelligence

Execution graphs replace single-model requests:

- Workflow nodes may include classification, generation (with fan-out), validators, judges, repairs, selectors, tool calls, streaming composition, and speculative decomposition.
- Steps react to conditional transitions (`verification_failed`, `tool_error`).
- Providers are grouped into capability pools curated via a live registry tracking: context windows, tool support, JSON compliance, streaming quality, refusal behavior, multilingual/code performance, long-context recall, latency percentiles, cost/quota state, and historical success rates by workload family.
- Registry refreshed via nightly/on-demand benchmarks (JSON compliance, code, summarization, retrieval, streaming, latency).

## Context Engineering & Validation

Context optimizer replaces simple prompt compression:

- **Salience ranking** chooses chunks by marginal value.
- **Context packing** fits instructions, memory, facts, tool outputs, scratch lanes into provider budgets.
- **Learned summaries** memorize goals, unresolved questions, preferences, decisions.
- **Structured lanes** separate instructions, memory, tool outputs, and scratch notes.
- **Provider-specific rewrites** tailor prompts (e.g., JSON-heavy, chain-of-thought, token-limited).

Validation pipeline includes:

1. **Structural validators** (orjson, jsonschema, AST, Markdown/table lint, tool-call syntax).
2. **Semantic checkers** (spaCy heuristics, evidence consistency).
3. **Judges** (async LLM scoring).

Failures trigger **repair FSMs** that retry with stronger prompts, different providers, deterministic decoding, or structured outputs (max 4 attempts). Repair success is tracked in `OutcomeRecord`.

## Semantic Cache, Streaming & Resilience

- Semantic cache uses datasketch MinHash + LSH (threshold default 0.92) to dedupe prompts and responses.
- Streaming uses SSE proxies with bounded `asyncio.Queue` backpressure (queue size = 32) and cancellation on disconnect.
- Resilience layers include Lua-backed circuit breakers, EWMA budget forecaster, AIMD concurrency controller, brownout mode (reduces enrichment under degradation), partial provider degradation detection, chaos mode injections, and deterministic resume for streaming/long-running agents.

## Agent Runtime & Observability

- Agent runtime coordinates tool-aware routing, step budgets, loop controls (timeouts, recursion, tool permissions, approval gates) and stores durable state (`msgpack` in Redis).
- Replay mode replays routing history, tool outputs, and deterministic prompts.
- Observability extends Prometheus/OpenTelemetry with semantic metrics: schema pass/fail, retry taxonomy, hallucination flags, tool accuracy, grounding score, prompt compression savings, provider drift, dissatisfaction proxies.
- Grafana dashboards: Operations, Quality, Routing Intelligence.

## Tenancy, Policy & Economics

- Tenants declare policy via DSL over providers/geographies, cost & latency ceilings, privacy/retention, tool restrictions, citation/schema mandates, and fallback strategies.
- Economic engine optimizes cost-per-success, reserves premium budgets, arbitrages bursts (cross-provider when one is cheaper/faster), enforces SLA tiers (bronze → platinum), and forecasts token futures to pre-route before exhaustion.
- Security layers enforce tenant secrets isolation, KMS encryption, outbound redaction, PII masking, signed audit trails, jailbreak defenses, and provenance labels per document/tool.

## Experimentation & Public Leaderboard

- Built-in experimentation supports shadowing, A/B routing, canary providers, replay simulators, offline evaluators, and what-if scoring.
- Public leaderboard (hourly/ nightly) publishes aggregated metrics while preserving privacy: best provider per task family, latency percentiles, schema compliance, long-context recall, budget states, benchmark history, anomaly alerts.

## Standards & Build Plan

- Engineering standards include strict mypy, no bare `except`, async discipline, zero blocking I/O, structured logging with request IDs, rigorous testing (≥85% coverage on core/providers/shared), resilient Docker builds (<200MB, non-root, health checks), and disaster-proof error handling.
- **14-day build plan** sequences deliverables: from OpenAI wire format + models to streaming, circuits, budget, profiler axes, routing engine, resilience, context pipeline, validation/repair, DAG engine, control plane + experiments, observability + Docker stack, culminating in docs/CI/readme packaging.

## Lifecycle Summary

1. Ingress validates OpenAI requests → workload profile + context lanes.
2. Policy-driven router scores candidates via expected utility + policy DSL.
3. Execution DAG runs providers with validators, judges, repairs, tool steps, hedges, and streaming.
4. Validators ensure correctness; repair FSMs fix failures.
5. Agents store durable state and replay paths deterministically.
6. Outcome records feed learning loops, capability registry, experiments, and dashboards.
