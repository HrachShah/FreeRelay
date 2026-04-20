# FreeRelay Developer Guide

Welcome to FreeRelay! This guide will help you understand how to integrate with FreeRelay, how our routing logic works, and how to get the most out of your dashboard.

## 1. Introduction

FreeRelay is an intelligent AI gateway designed to reduce LLM API costs by 20–40% while improving reliability. It acts as a transparent proxy for your OpenAI/Anthropic calls, automatically routing requests to the most cost-effective viable model based on the task's complexity.

### Key Benefits
- **Cost Savings**: Automatically use free or cheaper models for simple tasks.
- **Reliability**: Built-in fallback logic and circuit breakers.
- **Observability**: Real-time tracking of spend, tokens, and ROI.
- **OpenAI Compatible**: Drop-in replacement for any OpenAI-compatible SDK.

---

## 2. Authentication & API Keys

FreeRelay uses a custom API key system to identify users and organizations.

### API Key Format
All FreeRelay API keys start with the `fr_` prefix (e.g., `fr_live_...`). These keys are securely hashed using SHA-256 before being stored in our database.

### Getting an API Key
1. **Self-Serve Registration**: New users can register via the `/v1/auth/register` endpoint or through the dashboard.
2. **Dashboard Management**: You can create, copy, and revoke API keys from the **API Keys** section of the dashboard.

### Using your API Key
Pass your FreeRelay API key in the `Authorization` header just like you would with OpenAI:

```bash
Authorization: Bearer fr_your_key_here
```

---

## 3. Core Concepts

### Routing Modes
FreeRelay supports three primary routing modes, configurable via the `model` parameter in your request:

| Mode | Target Model ID | Description |
|------|-----------------|-------------|
| **Free** | `freerelay-free` | Routes only to free providers (Groq, Google AI Studio, etc.). |
| **Paid** | `freerelay-paid` | Routes only to high-quality paid providers (OpenAI, Anthropic). |
| **Auto** | `freerelay-auto` | **Recommended.** Intelligently switches between free and paid based on task complexity. |

### Cost-Aware Routing
Our routing engine evaluates every request against a **Capability Matrix**. It calculates a **Utility Score** for each available model based on:
- **Task Family**: Is it coding, chat, extraction, or creative writing?
- **Precision Sensitivity**: Does the task require high accuracy?
- **Current Latency**: Which provider is responding fastest right now?
- **Actual Cost**: What is the USD price per token?

The engine selects the model with the highest utility, ensuring you never overpay for simple requests.

### Fallback & Resilience
If a primary model fails (e.g., rate limits, downtime), FreeRelay automatically tries the next best model in the queue. This happens transparently to your application, significantly reducing 429 and 5xx errors.

---

## 4. Savings & ROI Tracking

FreeRelay tracks every token to show you exactly how much you're saving.

### How Savings are Calculated
1. **Baseline Cost**: We calculate what the request *would* have cost if sent directly to a premium model (e.g., GPT-4o).
2. **Actual Cost**: The actual cost incurred using the routed model.
3. **Savings**: `Baseline Cost - Actual Cost`.

### ROI Dashboard
Your dashboard provides high-level metrics:
- **Total Spend**: Actual amount spent through FreeRelay.
- **Total Savings**: The amount of money kept in your pocket.
- **Efficiency Score**: A percentage representing how well your workloads are being optimized.
- **Optimization Trends**: Visual charts showing spend vs. savings over time.

---

## 5. Integration Guide

### Python (OpenAI SDK)
Simply change the `base_url` and `api_key`.

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.freerelay.dev/v1", 
    api_key="fr_your_key_here"
)

response = client.chat.completions.create(
    model="freerelay-auto",
    messages=[{"role": "user", "content": "Summarize this article..."}]
)

print(response.choices[0].message.content)
```

### LangChain
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="https://api.freerelay.dev/v1",
    api_key="fr_your_key_here",
    model="freerelay-auto",
)
```

### Node.js / TypeScript
```typescript
import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'https://api.freerelay.dev/v1',
  apiKey: 'fr_your_key_here',
});
```

---

## 6. Dashboard Features

### Request Explorer
The **Request Explorer** provides "Glass Box" transparency into every decision FreeRelay makes.
- **Audit Logs**: See the exact model used, latency, and token breakdown for every request.
- **Decision Reasons**: Each log includes a "Reason" field (e.g., "Cost: GPT-4o-mini is cheapest viable model").
- **Filtering**: Filter by date, model, or status to debug your usage.

### API Key Management
Manage multiple keys for different environments (Dev, Staging, Production) and set optional usage limits per key (coming soon).

---

## 7. Billing & Tiers

FreeRelay offers metered billing integrated with **Stripe**.
- **Free Tier**: Limited monthly tokens, access to free models only.
- **Pro/Bronze Tier**: Access to all models, metered billing based on actual usage, and higher rate limits.

Upgrading is easy via the **Billing** section of the dashboard, which creates a Stripe Checkout session linked to your FreeRelay organization.

---

## 8. Support & Feedback

Need help?
- **Documentation**: [https://docs.freerelay.dev](https://docs.freerelay.dev)
- **GitHub Issues**: [https://github.com/HrachShah/FreeRelay/issues](https://github.com/HrachShah/FreeRelay/issues)
- **Email**: support@freerelay.dev
