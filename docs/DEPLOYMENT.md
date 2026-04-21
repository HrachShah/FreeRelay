# FreeRelay Deployment Guide

This document provides instructions for deploying FreeRelay in a production environment.

## Architecture Overview

FreeRelay consists of two main components:
1.  **Backend (FastAPI)**: The AI Gateway that handles request profiling, routing, and provider integration.
2.  **Dashboard (Next.js)**: A web interface for users to manage API keys, view analytics, and track savings.

## 1. Prerequisites

- **Supabase**: Used for authentication, API key management, and usage tracking.
- **Stripe** (Optional): Used for metered billing and user tiers.
- **Redis** (Optional): Used for distributed rate limiting, circuit breakers, and budget tracking.

## 2. Backend Deployment (FastAPI)

The backend is a FastAPI application that can be deployed to any Docker-compatible host (e.g., Railway, Render, Fly.io, or AWS).

### Environment Variables

Configure the following environment variables (see `.env.example` for details):

| Variable | Description |
| --- | --- |
| `FREERELAY_MODE` | Routing mode: `auto` (recommended), `free`, or `paid`. |
| `FREERELAY_PORT` | Port to run the server on (default: `8000`). |
| `FREERELAY_API_KEY` | Admin API key for the gateway (optional). |
| `FREERELAY_ENABLE_SUPABASE_AUTH` | Set to `true` to enable multi-tenant auth. |
| `FREERELAY_SUPABASE_URL` | Your Supabase project URL. |
| `FREERELAY_SUPABASE_KEY` | Your Supabase Anon/Public key. |
| `FREERELAY_SUPABASE_SERVICE_ROLE_KEY` | Your Supabase Service Role key (for admin tasks). |
| `GROQ_API_KEY`, `GOOGLE_AI_KEY`, etc. | API keys for LLM providers. |
| `FREERELAY_STRIPE_SECRET_KEY` | Stripe Secret Key for payments. |
| `FREERELAY_STRIPE_WEBHOOK_SECRET` | Stripe Webhook Secret for processing payments. |
| `FREERELAY_ENABLE_REDIS` | Set to `true` to enable Redis integration. |
| `FREERELAY_REDIS_URL` | Redis connection string (e.g., `redis://localhost:6379`). |

### Database Setup

1.  Create a new Supabase project.
2.  Go to the SQL Editor and run the contents of `supabase_schema.sql` to create the required tables and indices.

### Deployment via Docker

Use the provided `docker/Dockerfile`:

```bash
docker build -t freerelay-backend -f docker/Dockerfile .
docker run -p 8000:8000 --env-file .env freerelay-backend
```

### Deployment via Railway (Recommended)

1.  Fork the repository.
2.  Create a new project on Railway and link your fork.
3.  Railway will automatically detect `railway.json` and `docker/Dockerfile`.
4.  Add the environment variables in the Railway dashboard.

## 3. Frontend Deployment (Next.js)

The dashboard is a Next.js application located in the `dashboard/` directory.

### Environment Variables

| Variable | Description |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | The public URL of your deployed FreeRelay backend. |
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL. |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Your Supabase Anon/Public key. |

### Recommended: Vercel

The easiest way to deploy the dashboard is via Vercel:

1.  Connect your GitHub repository to Vercel.
2.  Set the **Root Directory** to `dashboard`.
3.  Add the environment variables.
4.  Deploy.

### Alternative: Static Export (Self-Hosted)

If you wish to serve the dashboard from the FastAPI backend:

1.  Enable static export in `dashboard/next.config.ts`:
    ```typescript
    const nextConfig: NextConfig = {
      output: 'export',
    };
    ```
2.  Build the project:
    ```bash
    cd dashboard
    npm install
    npm run build
    ```
3.  The built files will be in `dashboard/out`. Update the FastAPI `StaticFiles` mount in `freerelay/main.py` to point to the `out` directory.

## 4. Production Checklist

- [x] Supabase schema applied.
- [x] Provider API keys configured in backend.
- [ ] CORS allowed origins restricted in `freerelay/main.py` (currently set to `*` for MVP).
- [ ] `FREERELAY_LOG_FORMAT` set to `json`.
- [ ] SSL enabled on both backend and frontend.
- [ ] Stripe webhooks configured.
