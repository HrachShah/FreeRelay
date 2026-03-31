# FreeRelay Complete Spec

## Vision

FreeRelay must graduate from an OpenAI-compatible gateway for free-tier providers into **a programmable inference control plane** that understands workloads, routes on outcomes, validates correctness, and continuously improves through feedback. The *max version* is an inference mesh with:

- **Workload understanding** that profiles every request on rich axes.
- **Outcome-aware routing** powered by policies, expected utility scoring, and learning from traffic.
- **Multi-step execution orchestration** over DAGs, judges, verifiers, and repair loops.
- **Reliability and correctness guarantees** with validators, repairs, idempotent resume, and hardened observability.
- **Control-plane-grade operations** via policy DSLs, tenancy primitives, experimentation, and multi-region control/data-plane separation.

## Workload Profiling

Replace the intent classifier with a **workload profiler** that extracts a structured profile before any routing decision. Profile axes include:

| Axis | Description |
|------|-------------|
| Task family | chat / extraction / coding / planning / tool-use / RAG / eval / agent loop |
| Required depth | shallow / medium / deep reasoning |
| Precision sensitivity | low / medium / high |
| Latency class | interactive / async / batch |
| Context topology | short / long / fragmented / structured / multimodal |
| Tool dependence | none / optional / mandatory |
| Determinism needs | low / replayable / strict |
| Safety posture | permissive / standard / locked-down |
| Output contract | prose / JSON / schema / code patch / tool calls |
| Economic policy | cheapest acceptable / balanced / best possible |

This profile becomes the fundamental input for routing, execution planning, and context engineering.

## Outcome-Aware Routing

Routing must transition from static metadata scoring to a learned **expected utility model**:

```
expected_utility =
  P(success | workload, provider, config)
  × quality_score_estimate
  × schema_success_prob
  × latency_utility
  × cost_utility
  × safety_utility
  × user_policy_weight
```

The router blends this utility with policy constraints and tenant-level DSL rules.

### Evaluation Feedback Loop

Every request emits a post-hoc outcome record containing:

- Provider chosen
- Alternative providers considered
- Output valid/invalid
- Schema pass/fail
- User accepted/retried/regenerated
- Tool execution success
- Latency & cost
- Hallucination signals
- Downstream task success

These signals drive a learning loop that adjusts success probabilities, quality scores, and policy weights over time.

## Execution DAG Engine

FreeRelay must stop thinking in terms of one request → one provider. Introduce a declarative **execution DAG runtime** that supports:

- Classification steps (cheap classifiers or profile-based triggers)
- Generation with fan-out, cheap-first escalation, and candidate pools
- Judges, verifiers, and validators (schema, tests, policy)
- Repair steps activated on verification failure (stronger prompts, better providers, structured decoding)
- Selectors/judges (consensus, confidence-weighted) plus provenance tracking
- Tool execution nodes, streaming composition, and optional speculative decomposition

Execution graphs allow conditional steps (`verification_failed`, `tool_error`) and re-use of provider pools.

## Executor Capability Intelligence

Capability metadata must evolve from static YAML to a **live registry** that records:

- Context length limits
- Tool support matrix
- JSON/schema compliance rate
- Streaming quality metrics
- Refusal behavior and safety posture
- Multilingual and code-edit performance
- Long-context recall and timeout frequency
- Latency percentiles
- Cost and provider quota state
- Historical success rates per workload family

Continuous benchmarking (nightly and on-demand) keeps the registry current. Benchmarks cover JSON adherence, code generation, tool call correctness, summarization faithfulness, retrieval grounding, streaming cadence, and latency under concurrency.

## Context Optimization

Prompt compression graduates into a full **context optimizer**:

1. **Salience ranking** so marginal utility, not just recency, determines which chunks survive.
2. **Context packing** that fits the highest-value mix of memory, docs, and dialogue into the token budget.
3. **Learned summarization memories** tracking goals, unresolved questions, user preferences, tool outputs, constraints, and decisions.
4. **Structured context lanes** (instructions, memory, retrieved facts, dialogue, tool outputs, scratch summaries) that keep signals organized.
5. **Prompt rewrite policies** that tailor wording per provider (JSON-heavy for strict models, explicit chain decomposition for weaker models, shorter tool descriptions for token-constrained routes).

## Validation & Repair

Outputs must pass **hard correctness layers**:

- Syntax/schema/JSON/tool-call validation
- AST parse and linting for code
- Markdown/table linting when applicable
- Semantic validation (evidence citations, tool consistency, contradiction detection)
- Completeness scoring

Validation failures trigger **repair loops**:

- Retry on the same provider with stricter constraints
- Escalate to providers with higher schema reliability
- Invoke repair prompts or structured decoding
- Lower temperature, enforce deterministic decoding, or restructure tool calls

## Agent Runtime Support

The platform becomes agent-native:

- **Tool-aware routing** considers tool accuracy, hallucination rates, argument correctness, and multi-tool planning competence.
- **Agent loop controls** (max steps, recursion limits, per-step timeouts, tool permission scopes, per-provider retry policies, human approval checkpoints).
- **Durable agent state store** for current plans, completed actions, tool outputs, reasoning summaries, rollback points.
- **Replayable sessions** that re-run with frozen prompts, recorded tool outputs, deterministic routing choices, and fixed provider versions.

## Tenancy & Policy Engine

Each tenant defines policy via a DSL that covers:

- Allowed/blocked providers or geographies
- Cost ceilings per request/day/month
- Latency SLOs
- Privacy and retention modes
- Tool usage restrictions or approvals
- Citation/schema requirements for RAG tasks
- Strongest-model requirements for high-risk domains
- Fallback and escalation strategies

Policy primitives feed routing, validation, observability, and control-plane decisions.

## Economic Engine

FreeRelay becomes a **market maker**:

1. **Optimize cost-per-success**, not cost-per-request.
2. **Global budget allocator** (reserve quota for premium workloads, offload batch jobs, keep headroom for interactive users).
3. **Burst arbitrage** (shift traffic when providers temporarily win on cost/latency/quality).
4. **SLA tiers**: bronze (cheapest acceptable) → platinum (hedged, verified, repair loop).
5. **Token futures** (forecast exhaustion windows and pre-route before pain).

## Reliability & Resilience

Extend circuit breakers, retries, and hedging:

- **Adaptive concurrency limits** per provider/model/key based on live error and latency signals.
- **Brownout mode** that disables expensive verification, reduces fan-out, and downgrades context enrichment when degradation is detected.
- **Partial provider degradation detection** (streaming broken vs. non-streaming, tools broken, JSON failure above token thresholds, region-specific collapse).
- **Sophisticated hedging** (delayed, percentile-triggered, cross-region, verification-only for critical workloads).
- **Deterministic resume** for streaming responses and long-running agent jobs.

## Observability & Dashboards

Move beyond base metrics/traces/logs with semantic observability:

- Schema pass/fail
- Retry cause taxonomy
- Hallucination suspicion signal
- Tool argument accuracy
- Retrieval grounding score
- Candidate-vs-winner comparison
- Prompt compression savings per workload family
- Provider drift over time
- User dissatisfaction proxies

Build three dashboards:

1. **Operations**: latency, failure, saturation, circuit state, cost.
2. **Quality**: schema validity, retry & acceptance rates, benchmark drift, validation coverage.
3. **Routing Intelligence**: decision breakdown (winner, losers, score components, policy constraints, confidence).

Operators must answer “why did this request go there?” within 20 seconds.

## Security & Trust

Enterprise-grade controls:

- Per-tenant secrets isolation and KMS-backed key encryption
- Outbound egress policies and request/response redaction
- PII detection and masking
- Signed audit trails and provider data retention registries
- Jailbreak/prompt-injection defenses and retrieval trust tiers
- Document/tool provenance labels

## Multi-Region & Plane Separation

Design for global traffic with:

- Stateless gateway pods and region-local Redis/cache
- Clear control-plane vs. data-plane split
- Global policy distribution, regional routing execution, and provider affinity tuning
- Edge admission layers and core execution nodes

### Plane Responsibilities

- **Control plane**: config, policies, capability registry, benchmark catalog, experiments, tenant admin, rollout control.
- **Data plane**: request handling, routing, execution, streaming, caching.

## Routing DSL Expansion

Routing rules must reason over workload profiles, tenant tiers, schema requirements, context length, benchmark scores, provider health, budget state, and time-of-day quota windows. Actions include:

- Prefer / require / exclude provider pools
- Fan-out a configurable number of candidates
- Enable validator chains or schema enforcement
- Adjust retry policies and hedging behavior
- Cap `max_tokens`, bound temperature, or enforce JSON mode
- Require human approval or structured decoding

## Experimentation Platform

Ship bundled experimentation:

- Traffic shadowing
- A/B routing experiments
- Canary providers
- Replay against historical traces
- Offline evaluator runs
- “What-if” scoring simulator
- Model migration analysis

Questions like “If we routed high-context multilingual tasks to Provider X last week, what would latency/cost/quality look like?” must be answerable.

## Roadmap

1. **Phase 1** — Harden v1 (provider adapters, circuit/budget correctness, streaming, observability, config ergonomics).
2. **Phase 2** — Workload-aware routing (profile, quality-aware scoring, per-workload benchmarking, schema reliability metrics).
3. **Phase 3** — Validated outputs (validators, repair loops, strict JSON/code flows).
4. **Phase 4** — Execution graphs (multi-model DAGs, judges, verifiers, agent orchestration runtime).
5. **Phase 5** — Control plane (tenant policy engine, admin UI, experiment engine, benchmark registry, multi-region rollout).
6. **Phase 6** — Category-defining version (open-source inference mesh / AI traffic OS / control plane for model execution).

## Strategic Moat

The moat is:

1. Decision quality (choosing the best execution path).
2. Outcome feedback (learning from actual results).
3. Reliability under chaos.
4. Validation and repair.
5. Operability (visibility and policy control).

## Highest-Leverage Upgrades

A. Replace intent classification with workload profiling.  
B. Add outcome-aware routing with feedback learning.  
C. Add validators and repair loops.  
D. Build multi-model DAG orchestration.  
E. Split control and data planes early.  
F. Continuously benchmark providers.

## Product Statement

FreeRelay becomes **“a programmable inference control plane that understands workloads, chooses optimal execution strategies, validates outputs, and continuously improves routing across any model provider.”**

## Reference Build Notes (from the docx/master spec)

- **What is FreeRelay:** a production-grade, self-hosted AI gateway that aggregates all free-tier LLM providers behind an OpenAI-compatible endpoint, handling routing, failover, rate limiting, caching, streaming, observability, and cost optimization without touching client code (point at `http://localhost:8000`).
- **Problem it solves:** fragmented free tiers, inconsistent formats/limits, rate-limit-induced failures, zero visibility, and redundant token costs.
- **Supported providers (baseline):** Groq, Google AI Studio, OpenRouter, Together, Mistral with their respective RPM/TPM/TPD budgets and model lists; keep the table up to date with provider docs.
- **Architecture layers:** ingress (auth, rate limits, idempotency, validation), intelligence (cache/compression/profiling), routing (capability matrix + expected utility), execution (provider adapters, streaming backpressure, hedging/retries), observability (OTel, Prometheus, structured logs).
- **Request lifecycle:** validate OpenAI request → auth/rate limit/idempotency → semantic cache → compression/context optimization → workload profiling → routing → execution (with hedging for latency critical) → streaming back → budget tracking/caching → observability emits spans/metrics/logs.
- **Project layout:** package under `freerelay/` with modules for config, routing, execution, intelligence, resilience, providers, middleware, tenancy, observability, dashboard, CLI, plus `docker/`, `docs/`, `tests/`, `.github/`.
- **OpenAI wire format:** all request/response/streaming models follow the spec; `ChatCompletionRequest` mirrors OpenAI fields (tools, messages, response_format, etc.), responses include usage/logprobs/choices, streaming uses delta messages + SSE chunks.
- **Provider differences:** Groq uses OpenAI-compatible API but lacks logprobs; Google AI Studio requires `generateContent` payload and query param key; OpenRouter/Together have OpenAI-like endpoints (OpenRouter needs extra headers and `:free` suffix), Mistral follows provider-specific patterns.
- **BaseProvider contract:** abstract class exposing `complete`, `stream`, and `estimate_tokens`; ensures all adapters implement streaming SSE and token estimation used by budget reasoning.
- **Circuit breaker & budget:** Redis-backed CLOSED/HALF_OPEN/OPEN states with threshold/window/recovery rules; EWMA forecaster predicts token burn and flags providers before hitting daily limits (`BudgetForecaster` tracks tokens per provider/key with safety margins).
- **Semantic cache + prompt compression:** use MinHash + LSH to detect similar prompts (configurable similarity threshold + TTL); compression pipeline has structural cleanup, summarization, deduplication, and quality gate.
- **Streaming/backpressure + hedging:** use bounded `asyncio.Queue` between provider stream and client to curb memory; hedged execution fires top 2 providers for latency-critical requests and cancels losers once winner responds.
- **Routing scoring:** extends earlier composite score (capability × budget × circuit × latency) into expected utility that also factors schema success, safety, cost, quality, and learned success probabilities, while supporting policy DSL overrides.
- **Prompt compression & context engineering:** maintain lanes (instructions/memory/facts/tool outputs), salience rankings, packing summaries, and provider-tailored prompt rewrites.
- **Observability stack:** Prometheus metrics, OpenTelemetry traces, and structured logs track schema pass/fail, compression savings, provider drift, retry taxonomy, and routing intelligence; dashboards for operations, quality, and routing decisions.
- **Tech stack:** fastapi, uvicorn, httpx, pydantic/settings, redis, datasketch, pyyaml, opentelemetry SDK/exporter, prometheus-client, structlog, typer, rich, watchdog, tiktoken, pytest/pytest-asyncio, respx, locust, mypy, ruff, hatchling.
- **Packaging & infra:** `pyproject.toml` uses hatchling; docker compose wires FreeRelay + Redis + Jaeger + Prometheus + Grafana; GitHub workflows cover CI (lint/type/test) and release flow (hatch build + PyPI publish).
- **15-day build order + launch plan:** per-spec plan ensures step-by-step builds (models, providers, streaming, resilience, routing, concurrency, caching, middleware, observability, tenancy, CLI, docs) culminating in coordinated release (Hacker News, Reddit, X) with tight engagement window.
- **Engineering standards:** mypy strict pass, no bare `except`, no blocking sleeps, no hardcoded strings (settings/YAML), Lua-based Redis atomic ops, async provider calls, docstrings/tests for public APIs, ≥80% core/providers coverage, Docker non-root.
