# Benchmarks

FreeRelay v3 MAX relies on continuous benchmarking to keep the capability registry accurate and to detect provider drift. Benchmark runs are scheduled nightly and can be executed on-demand.

## Goals

- Measure JSON/schema compliance per output contract.
- Evaluate latency percentiles (TTFT and total).
- Track tool-call correctness and error rates.
- Assess long-context recall and summarization faithfulness.
- Maintain historical performance per workload family.

## Benchmark Suites

Suites are organized by workload family:

- `json_compliance`: strict JSON outputs, schema adherence, tool-call formatting.
- `coding`: unit-test pass rates and AST correctness.
- `summarization`: factual consistency and coverage.
- `rag_grounding`: evidence alignment and citation correctness.
- `latency`: concurrency ramps and p50/p95/p99 tracking.
- `streaming`: chunk cadence, backpressure behavior, and cancellation.

## Data Sources

Benchmarks consume:

- Prompt sets in `tests/benchmark_suite/prompts/`
- Reference answers in `tests/benchmark_suite/reference_answers/`
- Synthetic fixtures for schema/JSON strictness

## Capability Registry Updates

Each run updates registry dimensions:

- `context_length`
- `tool_support`
- `schema_compliance_rate` by output contract
- `streaming_quality`
- `refusal_behavior`
- `multilingual_score`
- `code_edit_score`
- `long_context_recall`
- `latency_p50/p95/p99`
- `historical_success_rate` by task family

## Scoring

Scores are normalized to [0, 1] and stored per provider-model-suite:

```
freerelay:benchmark:results:{provider}:{model}:{suite}
```

The control plane consumes these scores to:

- adjust expected utility terms,
- dampen exploration for unstable providers,
- trigger anomaly detectors when metrics drift.

## Anomaly Detection

The anomaly detector flags:

- sudden latency regressions,
- schema compliance drops,
- spikes in tool-call failures,
- elevated refusal rates,
- budget exhaustion anomalies.

Flags are recorded and can drive automatic policy updates (e.g., reduce fanout, disable hedging, or block a provider temporarily).

## Running Benchmarks

Benchmarks are scheduled via the control plane and can be invoked manually through the CLI:

```
freerelay benchmark --requests 50 --concurrent 10
```

## Publishing Results

Aggregated results (no user data) feed the public leaderboard:

- best provider per task family
- latency p50/p95/p99 by provider/model
- schema compliance by output contract
- benchmark score history (30 days)
