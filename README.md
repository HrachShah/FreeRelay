<p align="center">
  <br/>
  <img src="https://img.shields.io/badge/⚡_FreeRelay-AI_Gateway-8b5cf6?style=for-the-badge&labelColor=0a0a0f&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSIjOGI1Y2Y2Ij48cGF0aCBkPSJNMTMgMkw0IDE0aDdsLTEgOCAxMC0xMmgtN2wxLTh6Ii8+PC9zdmc+" alt="FreeRelay">
  <br/><br/>
</p>

<h1 align="center">FreeRelay</h1>

<p align="center">
  <strong>The open-source AI gateway that intelligently routes between free and paid LLMs.</strong>
</p>

<p align="center">
  <a href="https://github.com/HrachShah/FreeRelay/actions"><img src="https://img.shields.io/github/actions/workflow/status/HrachShah/FreeRelay/ci.yml?style=flat-square&label=CI" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12+-3776ab?style=flat-square" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
  <img src="https://img.shields.io/badge/free_providers-5-8b5cf6?style=flat-square" alt="5 Free Providers">
  <img src="https://img.shields.io/badge/paid_providers-2-f59e0b?style=flat-square" alt="2 Paid Providers">
  <img src="https://img.shields.io/badge/openai_compatible-100%25-06b6d4?style=flat-square" alt="OpenAI Compatible">
</p>

---

## The Problem

- **Free AI tiers are fragmented.** Groq, Google AI Studio, OpenRouter, Together, Mistral — all have free tiers with different formats, limits, and reliability.
- **Rate limits break your app.** You hit a 429 and your entire pipeline stops.
- **No smart routing.** Simple tasks waste premium credits, complex tasks fail on free tiers.

## The Solution

FreeRelay is a **self-hosted AI gateway** that automatically chooses the best provider for each request.

- **Free mode**: Uses only free providers (Groq, Google, OpenRouter, etc.)
- **Paid mode**: Uses OpenAI, Anthropic for maximum quality
- **Auto mode**: Free by default, intelligently switches to paid for complex tasks

```
┌────────────────┐       ┌────────────────────────────────────────┐
│   Your App     │       │          FreeRelay Gateway             │
│                │       │                                        │
│  OpenAI SDK    │──────▶│  Task Complexity Detection            │
│  LangChain     │       │  Smart Provider Routing               │
│  raw HTTP      │       │  Circuit Breakers + Fallback          │
│                │       │  Budget Forecasting                   │
└────────────────┘       └─────────────┬──────────────────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
          ▼                            ▼                            ▼
   ┌─────────────┐             ┌─────────────┐              ┌─────────────┐
   │   FREE      │             │   FREE     │              │    PAID     │
   │   tier      │             │   tier     │              │    tier     │
   │  Groq       │             │  OpenAI    │              │  GPT-4      │
   │  Google     │             │  Anthropic │              │  Claude     │
   └─────────────┘             └─────────────┘              └─────────────┘
```

## ⚡ Quick Start

```bash
# Install & run - works out of the box!
pip install -e . && freerelay
```

That's it! FreeRelay runs in **auto mode** at `http://localhost:8000`.

### Guided Setup

```bash
# Interactive setup to add API keys
freerelay setup
```

### Test it

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
```

### Use with OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

response = client.chat.completions.create(
    model="freerelay-auto",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)
```

## Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `free` | Only free providers | Budget-conscious apps |
| `paid` | Only OpenAI/Anthropic | Maximum quality |
| `auto` | Free + paid routing | **Recommended** - smart switching |

**Auto mode** automatically routes complex tasks (deep analysis, coding, large context) to paid providers while keeping simple tasks on free tier.

## Supported Providers

### Free Tier

| Provider | Models | RPM | Best For |
|----------|--------|-----|----------|
| **Groq** | llama-3.1, mixtral-8x7b | 30 | ⚡ Speed |
| **Google** | gemini-1.5-flash | 15 | 🌐 Large context |
| **OpenRouter** | llama-3.1, mistral-7b | 20 | 🔄 Most models |
| **Together AI** | llama-3.1, qwen2 | 60 | 📦 Batch |
| **Mistral** | mistral-small | — | 🇫🇷 Multilingual |

### Paid Tier

| Provider | Models | Best For |
|----------|--------|----------|
| **OpenAI** | gpt-4o, gpt-4o-mini | 🌟 Best overall |
| **Anthropic** | claude-3.5-sonnet | 📝 Long context |

## Configuration

```bash
# .env file
FREERELAY_MODE=auto           # free, paid, or auto

# Free providers
GROQ_API_KEY=sk-...
GOOGLE_AI_KEY=...

# Paid providers (optional)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
```

## Features That Set FreeRelay Apart

FreeRelay implements the **v3 MAX inference specification** documented in [docs/free_relay_v3_max_spec.md](docs/free_relay_v3_max_spec.md) (originally authored as FreeRelay_v3_MAX.zip). The spec describes an inference operating system that profiles every request, routes on expected outcomes, orchestrates declarative DAGs, validates/repairs, and keeps a policy-grade control plane buzzing behind the scenes.

### 🧠 Workload Profiling & Context Engineering
Every request is profiled on ten axes (task family, depth, precision, latency class, context topology, tools, determinism, safety, output contract, and economics) in under 5ms without any LLM calls. A context optimizer salience-ranks history, packs the highest-value lanes (instructions, memory, facts, tools, scratch), and rewrites prompts per provider signature before execution.

### ⚖️ Outcome-Aware Routing & Policy Engine
The router scores every provider-model on an expected utility formula that blends learned success probabilities, judge-derived quality scores, schema-compliance estimates, latency/cost/safety utilities, tenant policy weights, circuit state, budget health, and a UCB exploration bonus. Policy DSL rules can prefer/require/exclude providers, cap temperature, enable hedging, or fuse validators before the highest-utility decision is made.

### 🧵 Multi-Step Execution DAG & Validation
Execution graphs replace one-shot requests. Workflows chain classifiers, generators, validators, judges, repair FSMs, tool nodes, speculative decomposers, and hedging strategies with conditional transitions (verification_failed, tool_error, etc.). Validation happens in tiers—structural (JSON/AST/schema), semantic (heuristics, spaCy), and asynchronous judges—and failures trigger repair attempts (stronger prompts, deterministic decoding, provider escalation) before the response leaves the system.

### 🛡️ Correctness, Resilience & Streaming
Circuit breakers (Lua-backed CLOSED/HALF_OPEN/OPEN), EWMA budget forecasting, AIMD concurrency, brownout, and chaos-mode resilience protect downstream clients. Streaming uses backpressured SSE proxies with bounded queues and deterministic resume for long-running jobs. Semantic caching (datasketch MinHash + LSH) dedupes prompts, while observability (Prometheus + OpenTelemetry + structured logs) surfaces schema pass rates, retry taxonomies, hallucination signals, and provider drift.

### 🛰️ Control Plane, Economics & Leaderboard
The control plane owns tenant policy objects, capability registry, benchmark catalog, experiments (shadowing, A/B routing, replay simulators, what-if scoring), and the economic engine. Policies cover allowed providers/geographies, cost/latency ceilings, tool restrictions, and fallback chains. Economics optimize cost-per-success, reserve premium budgets, arbitrage bursts, enforce SLA tiers, and forecast token futures. A public leaderboard (hourly aggregates) spots the best provider per task family and keeps privacy intact.

## Feature Comparison

| Feature | FreeRelay | OpenRouter | Portkey | Helicone |
|---------|-----------|------------|---------|----------|
| Outcome-aware routing | ✓ | Partial | – | – |
| Multi-step execution DAGs | ✓ | – | – | – |
| Validation & repair loops | ✓ | – | – | – |
| Policy DSL + experimentation | ✓ | – | – | – |
| Streaming backpressure | ✓ | ✓ | ✓ | N/A |
| OpenAI SDK compatible | ✓ | ✓ | ✓ | ✓ |



## Use With Your Favorite Tools

<details>
<summary><strong>Continue.dev (VS Code)</strong></summary>

```json
{
  "models": [{
    "title": "FreeRelay",
    "provider": "openai",
    "model": "freerelay-auto",
    "apiBase": "http://localhost:8000/v1"
  }]
}
```
</details>

<details>
<summary><strong>LangChain</strong></summary>

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
    model="freerelay-auto",
)
```
</details>

<details>
<summary><strong>Node.js / TypeScript</strong></summary>

```typescript
import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'http://localhost:8000/v1',
  apiKey: 'not-needed',
});
```
</details>

<details>
<summary><strong>Open WebUI</strong></summary>

Set the OpenAI API base to `http://localhost:8000/v1`. No API key needed.
</details>

## Docker

```bash
cd docker
docker compose up -d
```

Starts: FreeRelay + Redis + Jaeger + Prometheus + Grafana

| Service | URL |
|---------|-----|
| FreeRelay API | http://localhost:8000 |
| Dashboard | http://localhost:8000/dashboard |
| Jaeger UI | http://localhost:16686 |
| Prometheus | http://localhost:9091 |
| Grafana | http://localhost:3000 (admin/freerelay) |

## CLI

```bash
# Install as CLI tool
pip install -e .

# Start the gateway
freerelay start

# Start with chaos mode
freerelay start --chaos

# Check provider status
freerelay status

# Run a quick benchmark
freerelay benchmark --requests 50 --concurrent 10
```

## Project Structure

```
freerelay/
├── freerelay/
│   ├── main.py                    # FastAPI app factory
│   ├── config/
│   │   ├── settings.py            # Pydantic BaseSettings
│   │   ├── capability_matrix.yaml # Provider/model capability DB
│   │   └── routing_rules.yaml    # Routing policy DSL
│   ├── core/
│   │   ├── models/openai.py       # Full OpenAI wire format (Pydantic v2)
│   │   ├── routing/engine.py      # Composite scoring router
│   │   ├── routing/classifier.py  # Intent classification
│   │   ├── execution/hedging.py   # Speculative parallel execution
│   │   ├── streaming/backpressure.py
│   │   └── resilience/
│   │       ├── circuit_breaker.py # CLOSED→OPEN→HALF_OPEN
│   │       ├── budget.py          # EWMA budget forecaster
│   │       └── chaos.py           # Chaos engineering injector
│   ├── providers/                 # Groq, Google, OpenRouter, Together, Mistral
│   ├── middleware/                # Auth, audit
│   ├── observability/             # Prometheus, structlog, health probes
│   └── cli/                       # Typer CLI
├── tests/                         # Unit + integration tests
├── docker/                        # Dockerfile + compose stack
├── dashboard/index.html          # Real-time monitoring dashboard
└── docs/                          # Architecture documentation
```

## How Routing Works

1. **Request arrives** → Validated against OpenAI schema
2. **Intent classified** → coding / math / creative / multilingual / chat (< 5ms)
3. **Providers scored** → `capability × budget × circuit_state × (1/(1 + p95_latency))`
4. **Best provider selected** → Request forwarded
5. **On failure** → Circuit breaker updated, next provider tried automatically
6. **After response** → Tokens tracked, budget updated, metrics emitted

## FreeRelay v3 MAX Specification

FreeRelay is grounded in the v3 MAX inference operating system documented in [docs/free_relay_v3_max_spec.md](docs/free_relay_v3_max_spec.md) and the bundled FreeRelay_v3_MAX.zip. The spec lays out the complete control/data-plane split, Redis schema, workload profile schema, routing decision audit trail, expected utility math, DAG engine, validators/repair loops, capability benchmarking, and the 14-day build plan that drives the repo roadmap.

Key capabilities the spec demands:

- Workload profiling (10 axes + context lanes) that feeds routing, elevators, and observability.
- Outcome-aware routing with expected utility, UCB exploration, policy DSL, validation directives, and hedge signals.
- Multi-step execution DAGs (classification → generation → validators → judges → repairs) plus tool-aware agents and speculative decomposition.
- Resilience: circuit breakers, EWMA budget forecasting, AIMD concurrency, brownout, chaos mode, deterministic resume, and streaming backpressure.
- Control-plane economics, experiments, tenant policy controls, signed audit trails, and the privacy-preserving public leaderboard.

## Roadmap

The v3 MAX spec embeds a 14-day build plan that keeps every merge focused on the same outcome: a workload-aware control plane with intelligent routing, validation, and experiments.

1. **Days 1-5** — Deposit the OpenAI wire format, provider adapters, streaming/backpressure, circuit breakers, budget forecasting, and multi-provider execution so requests reliably reach the best backend.
2. **Days 6-10** — Deliver the profiler (all ten axes), expected utility routing, semantic cache, context pipeline, validation layers, and repair FSMs so every response is intent-aware and correct.
3. **Days 11-14** — Ship the execution DAG engine, control-plane learner/benchmark/anomaly systems, observability/dashboards, Docker + compose stack, and final docs/CI/packaging polish.

Refer to [docs/free_relay_v3_max_spec.md](docs/free_relay_v3_max_spec.md) for the full day-by-day checklist and done criteria.

## Contributing

Contributions welcome. Start with [good first issues](https://github.com/HrachShah/FreeRelay/labels/good%20first%20issue).

```bash
git clone https://github.com/HrachShah/FreeRelay.git
cd FreeRelay
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT — use it however you want.

---

<p align="center">
  <strong>If this saved you money, star the repo ⭐</strong><br/>
  Built by <a href="https://github.com/HrachShah">@HrachShah</a>
</p>
