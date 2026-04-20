# FreeRelay Dashboard

## Tech Stack
- Next.js 14+ (App Router)
- Tailwind CSS
- Shadcn UI
- Recharts for data visualization
- Lucide React for icons

## Environment Variables
- `NEXT_PUBLIC_API_URL`: URL of the FreeRelay gateway (e.g., http://localhost:8000)

## Development
- Install dependencies: `npm install`
- Run dev server: `npm run dev`
- Build for production: `npm run build`

## Architecture
- `src/app`: Routes and pages.
  - `page.tsx`: Main ROI and savings dashboard.
  - `api-keys/page.tsx`: API key management.
  - `login/page.tsx`: Authentication (WIP).
- `src/components`: UI components (mostly Shadcn).
- `src/hooks`: Custom React hooks.

## Guidelines
- Follow standard Shadcn/Radix UI patterns.
- Use `use client` for interactive components.
- Ensure "Glass Box" transparency: clearly show Actual vs Baseline costs.
