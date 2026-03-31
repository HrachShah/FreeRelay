# FreeRelay Architecture

FreeRelay is no longer just a request router. It is a workload-aware inference control plane with five foundational pillars:

1. **Workload Profiling & Context Intelligence**  
   Every request triggers a workload profiler that emits structured axes (task family, depth, precision, latency class, tool dependence, safety posture, economic policy, etc.). A context optimizer then salience-ranks history, packs the highest-value chunks, maintains structured memory objects (goals, constraints, tool outputs, decisions), separates context lanes, and rewrites prompts for each model’s strengths before execution.

2. **Outcome-Aware Routing & Policy Engine**  
   A policy-guided routing DSL reasons over workload profiles, tenant tiers, schema requirements, budget/latency SLOs, provider health, and time windows. Expected utility mixing learned success probabilities, quality scores, schema reliability, latency/cost/safety utilities, and policy weights determines which path maximizes outcomes. Every decision emits a post-hoc outcome record to feed the learning loop.

3. **Execution DAG & Capability Intelligence**  
   Execution graphs replace “one request → one provider.” Declarative workflows support classification, fan-out generation, verifiers, validators, repairs, judges/selectors, speculative decomposition, and tool execution nodes. A live capability registry tracks context lengths, tool support, schema compliance, streaming quality, refusal behavior, multilingual/code performance, long-context recall, latency percentiles, quota state, and historical workload success metrics fueled by nightly/on-demand benchmarks.

4. **Reliability, Validation, & Observability**  
   Hard correctness layers validate syntax, JSON/schema, tool calls, AST/code, markdown, semantics, and completeness. Failing validations trigger repairs (retries, stronger prompts, provider escalation, deterministic decoding). Adaptive concurrency limits, brownout mode, partial degradation detection, advanced hedging (delayed, percentile, cross-region), and deterministic resumes keep traffic healthy. Semantic observability adds schema pass/fail, retry taxonomy, hallucination signals, tool accuracy, retrieval grounding, prompt compression savings per workload, provider drift, and user dissatisfaction proxies. Three dashboards (operations, quality, routing intelligence) let operators answer “why did this request go there?” in seconds.

5. **Control Plane & Tenancy Operations**  
   Control-plane services host configs, routing/tenant policies, capability registry, benchmark catalog, experiments, admin UI, rollout control, and multi-region distribution. Tenants declare DSL policies for allowed providers, blocked geographies, cost ceilings, latency SLOs, privacy modes, tool guardrails, citation/schema requirements, and fallback/escalation rules. Security layers enforce per-tenant secrets isolation, KMS-backed encryption, egress/redaction controls, PII masking, signed audit trails, jailbreak defenses, and retrieval provenance labels. The data plane handles hot-path request validation, routing, execution, streaming, caching, and agent state.

## Request Lifecycle

1. Ingress validates OpenAI wire requests, enforces auth and audit logging, and transforms state into workload profile + context lanes.
2. Workload profiler and context optimizer produce structured profiles and context bundles.
3. Routing DSL (rules + policy weights) scores providers via expected utility informed by capability intelligence and outcome history.
4. Execution DAG runtime constructs multi-model workflows with classifiers, generators, validators, judges, repairs, and tool nodes that may fan-out, fan-in, or execute sequentially.
5. Validators/semantic guards inspect outputs (schema, code, tool calls, evidence). Failures trigger repair loops or alternative providers as needed.
6. Agent runs persist state, respect loop controls, and can replay deterministically with frozen prompts, tooling, and routing.
7. Outcome data (success metrics, schema pass/fail, cost, latency, hallucination, downstream success) feeds the learning loop and updates capability registry.
8. Observability dashboards (operations, quality, routing intelligence) surfaces decision rationale, metric drift, and SLA coverage.

## Control/Data Plane Split

- **Control plane**: configuration management, tenant policy engine, DSL compiler, capability registry, benchmark runner, experimentation engine, admin UI, rollout control, and multi-region policy distribution.
- **Data plane**: request validation, workload profiling, context optimization, routing execution, multi-model DAG orchestration, streaming, caching, observability events, and agent runtime.

## Multi-Region & Edge Strategy

Stateless gateway pods live in each region with local Redis/cache for low-latency state; global control-plane services coordinate policies, experiments, and capability/state replication. Edge admission layers gate traffic before routing execution, ensuring regional provider affinity and failover.

## Observability & Analytics

Prometheus/OpenTelemetry provide foundational metrics, but semantic observability also tracks:

- Schema & validation pass rates
- Retry cause taxonomy
- Schema success vs. workload family
- Tool argument accuracy
- Retrieval grounding score
- Prompt compression savings (per profile)
- Provider drift warnings
- User dissatisfaction proxies (retries, rejects, severity)

Dashboards:

1. **Operations**: latency, failure budgets, circuit state, adaptive concurrency, cost burn.
2. **Quality**: schema validity, acceptance rates, benchmark drift, repair loop effectiveness.
3. **Routing Intelligence**: decision breakdown, score components (utility, policy weight), candidate vs. winner, confidence.

## Security & Reliability Considerations

- Adaptive concurrency & brownout guardrails protect providers.
- Sophisticated hedging (delayed, percentile, cross-region, verification-only) keeps critical workloads responsive.
- Deterministic resume handles streamed/long-running responses.
- Security enforces per-tenant secrets isolation, KMS encryption, redaction, PII masking, audit trails, jailbreak defenses, and provenance labeling.

## Tenancy, Policy & Economics

- Tenants define DSL policies (allow/deny providers, geographies, cost/latency ceilings, privacy, tool permissions, citation/schema requirements, fallback chains).
- Economic engine optimizes cost-per-success, allocates global budgets (reserve premium quota, offload batch), performs burst arbitrage, enforces SLA tiers (bronze → platinum), and reasons about token futures (forecast exhaustion & pre-routing).

## Experimentation & Feedback

Built-in experimentation supports:

- Traffic shadowing & A/B routing
- Canary providers & model migration analysis
- Replay on historical traces
- Offline evaluators & “what-if” scoring simulators

Outcome learning continuously updates success probabilities, quality scores, and policy weights.
