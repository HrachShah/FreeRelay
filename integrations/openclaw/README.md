# OpenClaw Integration

Integrate FreeRelay with OpenClaw to use free AI providers through a single, reliable endpoint.

## Quick Setup

### 1. Start FreeRelay

```powershell
pip install -e .; freerelay
```

### 2. Configure OpenClaw

Add this to your OpenClaw config file (usually `~/.openclaw/config.json5`):

```json5
{
  agents: {
    defaults: {
      model: { primary: "freerelay/groq-llama-3.1-70b" },
      models: {
        "freerelay/groq-llama-3.1-70b": {
          params: {
            baseUrl: "http://localhost:8000/v1",
            apiKey: "not-needed",
            api: "openai-chat",
            transport: "auto",
          },
        },
      },
    },
  },
}
```

### 3. Run OpenClaw

```bash
openclaw
```

## Available Models

FreeRelay automatically routes to the best available provider. Use any of these model names:

| Model Name | Provider | Best For |
|------------|----------|----------|
| `freerelay/groq-llama-3.1-70b` | Groq | Fast responses |
| `freerelay/google-gemini` | Google | Long context |
| `freerelay/openrouter-llama` | OpenRouter | Most models |
| `freerelay/together-qwen` | Together AI | Batch tasks |
| `freerelay/mistral-small` | Mistral | Multilingual |
| `freerelay/nvidia-llama` | NVIDIA | GPU optimized |

## Custom Configuration

### Use Auto Mode (Recommended)

FreeRelay in auto mode automatically uses free providers and switches to paid for complex tasks:

```json5
{
  agents: {
    defaults: {
      model: { primary: "freerelay/auto" },
      models: {
        "freerelay/auto": {
          params: {
            baseUrl: "http://localhost:8000/v1",
            apiKey: "not-needed",
            api: "openai-chat",
            transport: "auto",
          },
        },
      },
    },
  },
}
```

### Use Specific Provider

To force a specific provider:

```json5
{
  agents: {
    defaults: {
      model: { primary: "freerelay/groq" },
      models: {
        "freerelay/groq": {
          params: {
            baseUrl: "http://localhost:8000/v1",
            apiKey: "not-needed",
            api: "openai-chat",
            transport: "auto",
          },
        },
      },
    },
  },
}
```

## Environment Variables

Set these in your `.env` file before starting FreeRelay:

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

## Troubleshooting

### OpenClaw can't connect

1. Make sure FreeRelay is running: `freerelay`
2. Check the endpoint: `curl http://localhost:8000/v1/models`
3. Verify your `.env` has at least one API key

### Rate limiting

If you hit rate limits, FreeRelay will automatically switch to another provider. Check status:

```bash
freerelay status
```

### Changing port

If port 8000 is in use:

```bash
freerelay 8080
```

Then update your OpenClaw config to use `http://localhost:8080/v1`.
