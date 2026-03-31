# Workflow DSL

FreeRelay workflows define multi-step execution DAGs that replace single-model requests. Each workflow is a YAML file in `freerelay/config/workflows/` and compiles into a graph with conditional transitions, validators, judges, repair loops, and tool nodes.

## File Location

```
freerelay/config/workflows/
```

## Top-Level Schema

```yaml
version: 1
name: hard_coding
description: Fan-out + verify + repair + judge

nodes:
  - id: classify
    type: classifier
    model: cheap
    inputs: [request]
    outputs: [profile]

  - id: generate
    type: generate
    provider_pool: coding_pool
    fanout: 3
    inputs: [request, profile]
    outputs: [candidates]

  - id: validate
    type: validate
    validators: [schema, ast, tests]
    inputs: [candidates]
    outputs: [validated]

  - id: repair
    type: repair
    max_attempts: 4
    strategy: escalation
    inputs: [validated]
    outputs: [repaired]

  - id: judge
    type: judge
    async: true
    inputs: [repaired]
    outputs: [score]

  - id: select
    type: select
    method: confidence_weighted
    inputs: [repaired, score]
    outputs: [winner]

edges:
  - from: classify
    to: generate
  - from: generate
    to: validate
  - from: validate
    to: repair
    when: validation_failed
  - from: validate
    to: select
    when: validation_passed
  - from: repair
    to: validate
    when: repair_attempted
  - from: repair
    to: select
    when: repair_succeeded
```

## Node Types

Supported node types and their intent:

- `classifier`: cheap classification (rules or small model) to enrich routing context.
- `generate`: provider execution node; can fan-out to multiple providers/models.
- `validate`: structural/semantic validator chain.
- `repair`: finite-state repair loop; can retry or escalate provider pools.
- `judge`: async quality evaluator; emits scores without blocking response.
- `select`: consensus/aggregation stage to pick a winner from candidates.
- `tool`: tool call execution with retry controls and safety gates.
- `stream`: SSE streaming coordinator with backpressure.
- `merge`: merge outputs or partial results into a final response.

## Conditions

Edges can be guarded by conditions emitted by upstream nodes:

- `validation_failed`
- `validation_passed`
- `tool_error`
- `repair_attempted`
- `repair_succeeded`
- `hedge_fired`
- `timeout`

## Provider Pools

Provider pools are defined in routing policy and reference:

- Provider/model lists
- Minimum capability tier
- JSON/schema reliability thresholds
- Safety tiers
- Budget requirements

Example:

```yaml
provider_pools:
  coding_pool:
    require: [groq/llama-3.1-70b, google/gemini-1.5-flash]
    min_schema_success: 0.9
    min_safety_tier: 2
```

## Repair FSM

Repairs are a first-class node type with configurable strategies:

- `retry_same`: retry with stricter decoding.
- `escalation`: move to a stronger provider pool.
- `structured`: force JSON/schema modes.
- `rewrite`: apply prompt rewrite policies for strict output.

## Validation Layers

Validators can be stacked in `validate` nodes:

- Structural: JSON schema, AST, markdown lint, tool-call syntax.
- Semantic: heuristic checks (spaCy-based, grounding tests).
- Judge: async LLM judge (never blocks final response).

## Example Workflows

### Default (Single-shot + validation)

```yaml
name: default
nodes:
  - id: generate
    type: generate
    provider_pool: default_pool
    fanout: 1
  - id: validate
    type: validate
    validators: [schema]
  - id: select
    type: select
    method: best_first
edges:
  - from: generate
    to: validate
  - from: validate
    to: select
```

### Hard Coding (Fanout + repair)

```yaml
name: hard_coding
nodes:
  - id: generate
    type: generate
    provider_pool: coding_pool
    fanout: 3
  - id: validate
    type: validate
    validators: [schema, ast, tests]
  - id: repair
    type: repair
    max_attempts: 4
    strategy: escalation
  - id: select
    type: select
    method: confidence_weighted
edges:
  - from: generate
    to: validate
  - from: validate
    to: repair
    when: validation_failed
  - from: validate
    to: select
    when: validation_passed
  - from: repair
    to: validate
    when: repair_attempted
  - from: repair
    to: select
    when: repair_succeeded
```

## Operational Notes

- Workflow compilation happens at startup; invalid schemas fail fast.
- DAG execution preserves provenance for each candidate and validator.
- Conditional edges determine early exits or escalation to stronger pools.
