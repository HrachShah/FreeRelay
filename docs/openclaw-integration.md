# OpenClaw Integration Guide

FreeRelay is fully compatible with [OpenClaw](https://openclaw.ai) — the open-source AI agent platform. By routing OpenClaw through FreeRelay, you get workload-aware routing, validation, provider failover, and cost optimization across all free-tier LLM providers — without changing OpenClaw's config manually.

```
Chat apps → OpenClaw Gateway → FreeRelay → Free LLM Providers (Groq, Google, OpenRouter, Together, Mistral)
```

## Quick Setup

### Step 1 — Start FreeRelay

```bash
# Install and configure
cp .env.example .env
# Add at least one API key to .env

# Run
python -m freerelay.main
```

FreeRelay runs at `http://localhost:8000`.

### Step 2 — Get the OpenClaw config

FreeRelay exposes a config generator at `GET /openclaw/config`. Visit it in a browser or fetch it:

```bash
curl http://localhost:8000/openclaw/config
```

This returns the exact JSON fragment to merge into `~/.openclaw/openclaw.json`.

### Step 3 — Connect OpenClaw

**Option A: Use the onboard wizard (recommended)**

```bash
openclaw onboard --install-daemon
```

When prompted:
1. Choose **Manual** as the onboarding mode
2. Select **Custom** or **OpenAI-compatible** as the provider
3. Enter:
   - **Base URL**: `http://localhost:8000/v1`
   - **API Key**: `not-needed` (or your gateway key if `FREERELAY_API_KEY` is set)
   - **Model**: `freerelay/auto`

**Option B: Non-interactive (CI/scripted)**

```bash
openclaw onboard --non-interactive --accept-risk \
  --auth-choice apiKey \
  --token-provider custom \
  --custom-base-url "http://localhost:8000/v1" \
  --install-daemon --skip-channels --skip-skills
```

**Option C: Manual config edit**

Merge the output of `/openclaw/config` into `~/.openclaw/openclaw.json`:

```json
{
  "models": {
    "providers": {
      "freerelay": {
        "baseUrl": "http://localhost:8000/v1",
        "apiKey": "not-needed",
        "api": "openai-completions",
        "models": [
          { "id": "auto", "name": "FreeRelay Auto (workload-aware routing)" },
          { "id": "freerelay-groq", "name": "FreeRelay → Groq" },
          { "id": "freerelay-google", "name": "FreeRelay → Google" },
          { "id": "freerelay-openrouter", "name": "FreeRelay → OpenRouter" },
          { "id": "freerelay-together", "name": "FreeRelay → Together" },
          { "id": "freerelay-mistral", "name": "FreeRelay → Mistral" }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "freerelay/auto"
      },
      "models": {
        "freerelay/auto": {}
      }
    }
  }
}
```

### Step 4 — Verify

```bash
# Check OpenClaw health
openclaw health

# Check model status
openclaw models status

# Send a test message
openclaw agent --agent main -m "Hello, what model are you?"
```

## Available Models

| OpenClaw Model ID | Description |
|---|---|
| `freerelay/auto` | Workload-aware routing (recommended). FreeRelay profiles the request and picks the best provider. |
| `freerelay/freerelay-groq` | Route to Groq (fastest, llama-3.1-70b) |
| `freerelay/freerelay-google` | Route to Google AI Studio (gemini-1.5-flash, huge context) |
| `freerelay/freerelay-openrouter` | Route to OpenRouter (most model variety) |
| `freerelay/freerelay-together` | Route to Together AI (batch-friendly) |
| `freerelay/freerelay-mistral` | Route to Mistral AI (multilingual) |

## How It Works

1. OpenClaw sends OpenAI-format chat completion requests to FreeRelay
2. FreeRelay's **workload profiler** analyzes the request on 10 axes (task family, depth, precision, latency class, context topology, tool use, determinism, safety, output contract, economics)
3. The **expected utility router** scores each provider and selects the best one
4. If a provider fails, FreeRelay **automatically falls back** to the next-best provider
5. Responses stream back to OpenClaw in standard SSE format

This means OpenClaw agents get intelligent routing, automatic failover, budget management, and semantic caching — all without any OpenClaw-side configuration complexity.

## Per-Channel Model Override

Configure different FreeRelay models for different OpenClaw channels:

```json
{
  "telegram": {
    "agents": {
      "defaults": {
        "model": { "primary": "freerelay/auto" }
      }
    }
  },
  "discord": {
    "agents": {
      "defaults": {
        "model": { "primary": "freerelay/freerelay-groq" }
      }
    }
  },
  "slack": {
    "agents": {
      "defaults": {
        "model": { "primary": "freerelay/freerelay-google" }
      }
    }
  }
}
```

## Using with Auth Profiles

For secure credential management, use OpenClaw's auth profiles:

```json
{
  "auth": {
    "profiles": {
      "freerelay:default": {
        "provider": "freerelay",
        "mode": "api_key"
      }
    }
  }
}
```

Then set the key in your system keychain:

```bash
openclaw auth set freerelay:default --key "your-freerelay-api-key"
```

## API Endpoints

FreeRelay provides these OpenClaw-specific endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/openclaw/config` | GET | Returns the full `openclaw.json` config fragment |
| `/openclaw/config?base_url=http://host:port/v1` | GET | Config with custom base URL |
| `/openclaw/models` | GET | Models in OpenClaw-compatible format |
| `/v1/models` | GET | Standard OpenAI model listing |
| `/v1/chat/completions` | POST | Chat completions (OpenAI-compatible) |

## Troubleshooting

### "Connection refused" from OpenClaw

Make sure FreeRelay is running and accessible:

```bash
curl http://localhost:8000/health
```

If running in Docker, use the host IP or `host.docker.internal` instead of `localhost`.

### "Invalid model name"

The model name in OpenClaw must use the `freerelay/` prefix. Check available models:

```bash
curl http://localhost:8000/openclaw/models
```

### All providers failing

Check provider status:

```bash
curl http://localhost:8000/v1/stats
```

Ensure at least one API key is configured in `.env`.

### Streaming issues

FreeRelay supports SSE streaming. If OpenClaw has issues, try disabling streaming in your OpenClaw config or check that the base URL ends with `/v1` (not `/v1/`).

## Advanced: Using FreeRelay as LiteLLM Backend

If you're already using LiteLLM with OpenClaw, you can add FreeRelay as a LiteLLM provider too:

```yaml
# litellm_config.yaml
model_list:
  - model_name: freerelay-auto
    litellm_params:
      model: openai/freerelay-auto
      api_base: http://localhost:8000/v1
      api_key: not-needed
```

This gives you LiteLLM's cost tracking on top of FreeRelay's intelligent routing.
