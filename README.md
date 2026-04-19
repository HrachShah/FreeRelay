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
│  OpenAI SDK    │──────▶│  Task Complexity Detection             │
│  LangChain     │       │  Smart Provider Routing                │ 
│  raw HTTP      │       │  Circuit Breakers + Fallback           │
│                │       │  Budget Forecasting                    │
└────────────────┘       └─────────────┬──────────────────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
          ▼                            ▼                            ▼
   ┌─────────────┐             ┌─────────────┐              ┌─────────────┐
   │   FREE      │             │   FREE      │              |    PAID     │
   │   tier      │             │   tier      │              │    tier     │
   │  Groq       │             │  OpenAI     │              │    GPT-4    │
   │  Google     │             │  Anthropic  │              │    Claude   │
   └─────────────┘             └─────────────┘              └─────────────┘
```

## ⚡ Quick Start

```bash
# Install & run - works out of the box!
pip install -e .; freerelay
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
| **NVIDIA** | llama-3.1, mixtral | 40 | 🎮 GPU optimized |

### Paid Tier

| Provider | Models | Best For |
|----------|--------|----------|
| **OpenAI** | gpt-4o, gpt-4o-mini | 🌟 Best overall |
| **Anthropic** | claude-3.5-sonnet | 📝 Long context |

## 🔑 How to Get API Keys (Step by Step)

### Groq (Free)

1. Go to **https://console.groq.com/keys**
2. Click **Sign Up** (or **Log In** if you have an account)
3. Verify your email
4. Click **Create API Key**
5. Copy the key (starts with `gsk_...`)
6. Add to `.env`: `GROQ_API_KEY=gsk_your_key_here`

### Google AI Studio (Free)

1. Go to **https://aistudio.google.com/apikey**
2. Sign in with your Google account
3. Click **Create API Key**
4. Select a project (or create a new one)
5. Copy the key
6. Add to `.env`: `GOOGLE_AI_KEY=your_key_here`

### OpenRouter (Free)

1. Go to **https://openrouter.ai/keys**
2. Click **Sign Up** (or **Log In**)
3. Click **Create Key**
4. Give it a name (e.g., "FreeRelay")
5. Copy the key (starts with `sk-or-...`)
6. Add to `.env`: `OPENROUTER_API_KEY=sk-or-your_key_here`

### Together AI (Free)

1. Go to **https://api.together.xyz**
2. Click **Sign Up** or **Log In**
3. Go to **Settings** → **API Keys**
4. Click **Create new API key**
5. Copy the key
6. Add to `.env`: `TOGETHER_API_KEY=your_key_here`

### Mistral AI (Free)

1. Go to **https://console.mistral.ai/api-keys/**
2. Sign up or log in
3. Click **Create new key**
4. Give it a name
5. Copy the key
6. Add to `.env`: `MISTRAL_API_KEY=your_key_here`

### NVIDIA Build (Free)

1. Go to **https://build.nvidia.com/explore/recommended**
2. Click **Sign Up** (or **Log In**)
3. Go to **Settings** → **API Keys**
4. Click **Generate API Key**
5. Copy the key (starts with `nvapi-...`)
6. Add to `.env`: `NVIDIA_API_KEY=nvapi-your_key_here`

### OpenAI (Paid)

1. Go to **https://platform.openai.com/api-keys**
2. Sign up or log in
3. Click **Create new secret key**
4. Name it (e.g., "FreeRelay")
5. Copy the key (starts with `sk-...`)
6. Add to `.env`: `OPENAI_API_KEY=sk-your_key_here`

### Anthropic (Paid)

1. Go to **https://console.anthropic.com/settings/keys**
2. Sign up or log in
3. Click **Create Key**
4. Name it (e.g., "FreeRelay")
5. Copy the key (starts with `sk-ant-...`)
6. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-your_key_here`

## Configuration

After getting your API keys, edit `.env`:

```bash
# Mode: free, paid, or auto
FREERELAY_MODE=auto

# Free providers
GROQ_API_KEY=gsk_your_key_here
GOOGLE_AI_KEY=your_key_here
OPENROUTER_API_KEY=sk-or_your_key_here
TOGETHER_API_KEY=your_key_here
MISTRAL_API_KEY=your_key_here
NVIDIA_API_KEY=nvapi_your_key_here

# Paid providers (optional)
OPENAI_API_KEY=sk_your_key_here
ANTHROPIC_API_KEY=sk-ant_your_key_here
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
| OpenCode/Codex CLI backends | ✓ | – | – | – |
| Skills (coding-supervisor) | ✓ | – | – | – |



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

<details>
<summary><strong>OpenClaw</strong></summary>

FreeRelay has built-in OpenClaw integration. Start FreeRelay, then fetch the config:

```bash
# Start FreeRelay
python -m freerelay.main

# Get the OpenClaw config snippet
curl http://localhost:8000/openclaw/config
```

**Option A — Use the onboard wizard (recommended):**
```bash
openclaw onboard --install-daemon
# When prompted: Manual → Custom → Base URL: http://localhost:8000/v1 → Model: freerelay/auto
```

**Option B — Non-interactive:**
```bash
openclaw onboard --non-interactive --accept-risk \
  --auth-choice apiKey --token-provider custom \
  --custom-base-url "http://localhost:8000/v1" \
  --install-daemon --skip-channels --skip-skills
```

**Option C — Manual config (`~/.openclaw/openclaw.json`):**
```json
{
  "models": {
    "providers": {
      "freerelay": {
        "baseUrl": "http://localhost:8000/v1",
        "apiKey": "not-needed",
        "api": "openai-completions",
        "models": [
          { "id": "auto", "name": "FreeRelay Auto" },
          { "id": "freerelay-groq", "name": "FreeRelay → Groq" },
          { "id": "freerelay-google", "name": "FreeRelay → Google" }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": { "primary": "freerelay/auto" }
    }
  }
}
```

Then run:
```bash
openclaw gateway run
```

Use `freerelay/auto` as the model for workload-aware routing across all free providers.
For more details, see [docs/openclaw-integration.md](docs/openclaw-integration.md).
</details>

<details>
<summary><strong>OpenCode & Codex</strong></summary>

FreeRelay integrates with OpenCode as both an **API proxy** and **CLI backend**, plus Codex as a CLI backend.

**OpenCode API Proxy (Zen + Go catalogs):**
```bash
# Set your OpenCode API key
echo "OPENCODE_API_KEY=your_key_here" >> .env

# Use OpenCode Zen models (Claude, GPT, Gemini)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"freerelay/opencode-claude-sonnet","messages":[{"role":"user","content":"Hello"}]}'

# Use OpenCode Go models (Kimi, GLM, MiniMax)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"freerelay/opencode-kimi-k2","messages":[{"role":"user","content":"Write a function"}]}'
```

**List OpenCode models:**
```bash
curl http://localhost:8000/opencode/models
```

**CLI Backend (spawn OpenCode/Codex as subprocess):**
```bash
# Check which CLI backends are available
curl http://localhost:8000/opencode/cli-backends

# Run a coding task via OpenCode CLI
curl -X POST http://localhost:8000/opencode/cli-run \
  -H "Content-Type: application/json" \
  -d '{"backend":"opencode-cli","prompt":"Write a Python hello world","model":"opencode-claude-sonnet"}'

# Run via Codex CLI
curl -X POST http://localhost:8000/opencode/cli-run \
  -H "Content-Type: application/json" \
  -d '{"backend":"codex-cli","prompt":"Write a Python hello world"}'
```

**Skills:**
```bash
# List available skills
curl http://localhost:8000/skills

# Get skills config for OpenClaw
curl http://localhost:8000/skills/config
```

| Model ID | Catalog | Upstream |
|----------|---------|----------|
| `freerelay/opencode-claude-sonnet` | Zen | Claude Sonnet |
| `freerelay/opencode-claude-haiku` | Zen | Claude Haiku |
| `freerelay/opencode-gpt-4o` | Zen | GPT-4o |
| `freerelay/opencode-gemini-flash` | Zen | Gemini Flash |
| `freerelay/opencode-kimi-k2` | Go | Kimi K2 |
| `freerelay/opencode-glm-4` | Go | GLM-4 |
| `freerelay/opencode-minimax-01` | Go | MiniMax |

CLI backends communicate via JSONL subprocess with API keys cleared from the environment for security.
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

## 🚀 Deployment

### Railway (Recommended)

1. Fork this repository.
2. Create a new project on Railway and link your fork.
3. Add the required environment variables (see `.env.example`).
4. Railway will automatically detect the `railway.json` and `docker/Dockerfile` and deploy the gateway.

### Supabase Setup (Authentication & Usage Tracking)

FreeRelay supports Supabase for managing API keys and tracking usage.

1. Create a new Supabase project.
2. Run the SQL in `supabase_schema.sql` in the SQL Editor to create the necessary tables and indices.
3. Set `FREERELAY_ENABLE_SUPABASE_AUTH=true` and provide `SUPABASE_URL`, `SUPABASE_KEY`, and `FREERELAY_SUPABASE_SERVICE_ROLE_KEY` (for admin tasks like registration) in your environment.

### Stripe Integration (Payments)

FreeRelay includes basic Stripe integration for user upgrades.

1. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in your environment.
2. Configure `STRIPE_SUCCESS_URL` and `STRIPE_CANCEL_URL`.
3. Use the `/v1/billing/checkout` endpoint to create a checkout session.
4. Set up a Stripe webhook pointing to `https://your-domain.com/v1/billing/webhook` listening for `checkout.session.completed` events.

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
│   ├── providers/                 # Groq, Google, OpenRouter, Together, Mistral, OpenCode
│   ├── middleware/                # Auth, audit
│   ├── observability/             # Prometheus, structlog, health probes
│   ├── openclaw/                  # OpenClaw integration adapter
│   ├── cli_backend/               # OpenCode/Codex CLI subprocess backends
│   ├── skills/                    # Coding skills (OpenCode, Codex, Supervisor)
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
