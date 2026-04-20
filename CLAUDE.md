# FreeRelay - Team Documentation

## Project Goal
Enable developers to reduce LLM API costs by 20–40% while improving reliability through routing and fallback logic.

## Tech Stack
- **Backend**: FastAPI (Python)
- **Database**: Turso (SQLite) for team coordination, Supabase (PostgreSQL) for user data/logs.
- **Frontend**: Next.js (React), Tailwind CSS, Shadcn UI, Recharts.
- **Payments**: Stripe (Metered Usage).
- **Authentication**: Supabase Auth.

## Repository Structure
- `/freerelay`: Main AI gateway server and core logic.
  - `/core`: Routing engine, model definitions, and execution.
  - `/middleware`: Auth, audit, rate-limiting, idempotency.
  - `/observability`: Logging, metrics, health checks, and analytics.
  - `/shared`: Shared models and utilities.
- `/dashboard`: Next.js frontend for usage tracking and management.
- `/docs`: Architecture specifications and manuals.
- `/tests`: Integration and unit tests.

## Development Workflow
- **Linting**: `ruff`
- **Formatting**: `black`
- **Type Checking**: `mypy`
- **Testing**: `pytest`

## Key Commands
- Run Gateway: `python -m freerelay.main`
- Run Dashboard: `cd dashboard && npm run dev`
- Run Tests: `pytest`
