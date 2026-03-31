# Routing Rules DSL

FreeRelay’s routing rules DSL configures policy-driven decisions that reason over workload profiles, tenant tiers, schema/context requirements, provider health, budget state, and experimentation flags. Rules are evaluated in order; the first matching rule shapes the preferred provider pools and workflow configuration.

## File Location

```
freerelay/config/routing_rules.yaml
```

## Rule Schema

```yaml
version: 1

rules:
  - name: rule_name
    condition: "expression"
    actions:
      - prefer: [provider/model, ...]
      - require: [provider/model]
      - exclude: [provider/model]
      - fanout: 3
      - validators:
          - schema
          - tests
      - retry_policy: "strict"
      - set_temperature: 0.2
      - enforce_mode: json
      - require_hedging: critical
      - human_gate: true
    fallback: any|none
```

## Condition Expressions

Conditions may reference workload profile fields (`workload.task_family`, `workload.precision`, etc.), request telemetry, tenant metadata, or internal baseline signals:

| Variable | Description |
|----------|-------------|
| `workload.task_family` | `chat`, `extraction`, `coding`, `planning`, `tool_use`, `RAG`, `eval`, `agent_loop` |
| `workload.required_depth` | `shallow`, `medium`, `deep` |
| `workload.precision_sensitivity` | `low`, `medium`, `high` |
| `workload.latency_class` | `interactive`, `async`, `batch` |
| `workload.context_topology` | `short`, `long`, `fragmented`, `structured`, `multimodal` |
| `workload.tool_dependence` | `none`, `optional`, `mandatory` |
| `workload.determinism_needs` | `low`, `replayable`, `strict` |
| `workload.safety_posture` | `permissive`, `standard`, `locked_down` |
| `workload.output_contract` | `prose`, `JSON`, `schema`, `code_patch`, `tool_calls` |
| `workload.economic_policy` | `cheapest`, `balanced`, `best_possible` |
| `tenant.tier` | `bronze`, `silver`, `gold`, `platinum` |
| `schema.success_ratio` | Latest rolling schema success rate |
| `compression.savings` | Tokens removed by context optimizer |
| `provider.health.status` | `healthy`, `degraded`, `offline` |
| `budget.state` | `green`, `amber`, `red` |
| `time.daypart` | `business_hours`, `off_hours` |

Operators: `==`, `!=`, `>`, `<`, `>=`, `<=`, `in`, `not in`, `and`, `or`, parentheses for precedence.

### Examples

```yaml
- name: high_precision_coding
  condition: "workload.task_family == 'coding' and workload.precision_sensitivity == 'high'"
  actions:
    - prefer: [groq/llama-3.1-70b, google/gemini-1.5-flash]
    - validators: [schema, tests]
    - require_hedging: verification
    - fanout: 3
    - enforce_mode: json
  fallback: any

- name: async_batch_workloads
  condition: "workload.latency_class == 'batch' and tenant.tier != 'bronze'"
  actions:
    - prefer: [together/meta-llama/Llama-3.1-70B-Instruct-Turbo, mistral/mistral-small]
    - fanout: 2
    - set_temperature: 0.3
  fallback: any

- name: locked_down_tools
  condition: "workload.tool_dependence == 'mandatory' and workload.safety_posture == 'locked_down'"
  actions:
    - require: [openrouter/meta-llama/llama-3.1-8b-instruct:tools]
    - enforce_mode: json
    - human_gate: true
  fallback: none
```

## Policy Impact

Rules can set policy weights that influence utility computation (e.g., amplify safety utility for legal workloads, penalize cost for balanced tenants). The router merges rule-derived directives with capability intelligence and outcome learning to pick the highest-utility execution path while respecting tenant constraints.
