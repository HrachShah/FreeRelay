# FreeRelay Production Onboarding & Operations

This document describes the self-serve onboarding flow and operational guidelines for the FreeRelay production environment.

## 1. Self-Serve Onboarding Flow

FreeRelay is designed for developers to get started without manual intervention.

### Step 1: User Registration
Users register via the `/v1/auth/register` endpoint by providing their email.
- **Action**: `POST /v1/auth/register`
- **Payload**: `{"email": "user@example.com"}`
- **Response**: `{"api_key": "fr_live_..."}`
- **Note**: The system automatically creates a user in Supabase and generates a default API key.

### Step 2: Dashboard Access
Users can log into the dashboard to view their usage and manage additional API keys.
- **URL**: `https://freerelay.app/dashboard` (Mocked in local dev)
- **Features**: ROI visualization, key rotation, and usage breakdown.

### Step 3: Billing Setup (Optional but Recommended)
To access premium tiers (e.g., 'Bronze'), users can initiate a Stripe checkout.
- **Action**: `POST /v1/billing/checkout`
- **Payload**: `{"email": "user@example.com", "price_id": "price_..."}`
- **Result**: Redirects user to a hosted Stripe Checkout page.
- **Outcome**: Upon successful payment, the user's tier is automatically upgraded via webhook.

## 2. API Integration

### Base URL
The production API is accessible at `https://api.freerelay.app`.

### Authentication
Include the FreeRelay API key in the `Authorization` header:
```bash
Authorization: Bearer fr_live_your_key_here
```

### OpenAI Compatibility
FreeRelay follows the OpenAI API specification for Chat Completions.
```python
import openai

client = openai.OpenAI(
    base_url="https://api.freerelay.app/v1",
    api_key="fr_live_..."
)

response = client.chat.completions.create(
    model="auto",  # Use 'auto' for best cost/performance routing
    messages=[{"role": "user", "content": "Hello FreeRelay!"}]
)
```

## 3. Operational Monitoring

### Health Checks
- **Gateway Status**: `GET /v1/hello` or `GET /health`
- **Stats Endpoint**: `GET /v1/stats` (Internal usage metrics)

### Metrics
Prometheus metrics are exposed at `/metrics` for monitoring throughput, latency, and error rates per provider.

### Logs
System logs include per-request tracking of Baseline vs Actual costs, enabling real-time ROI auditing.
