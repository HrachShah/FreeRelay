# FreeRelay Dashboard

A modern Next.js dashboard for monitoring and controlling the FreeRelay inference control plane.

## Features

- Real-time monitoring of LLM requests across providers (OpenAI, Anthropic, Groq)
- Route configuration and management
- Analytics and usage tracking
- API key management

## Getting Started

1. Copy `.env.example` to `.env.local` and fill in your API keys
2. Install dependencies: `npm install`
3. Run the development server: `npm run dev`
4. Open [http://localhost:3000](http://localhost:3000)

## Environment Variables

| Variable | Description |
|----------|-------------|
| `FREERELAY_API_URL` | Base URL for FreeRelay API (default: http://localhost:8000) |
| `FREERELAY_API_KEY` | API key for authentication |
