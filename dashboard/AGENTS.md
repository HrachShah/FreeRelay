# FreeRelay Dashboard - Agent Guidelines

## Focus Areas
- **UI/UX Consistency**: Use Shadcn UI components for all dashboard elements.
- **ROI Visualization**: Prioritize "Savings Over Time" and "Cost Breakdown" (Actual vs Baseline).
- **Security**: Ensure API keys and user data are handled securely (WIP Supabase integration).

## Key Components
- `DashboardPage`: Main view showing total spend, tokens, and savings.
- `ApiKeysPage`: Management interface for user access tokens.
- `LoginPage`: Authentication entry point (WIP).

## Tech Stack Guidelines
- Use `lucide-react` for icons.
- Use `recharts` for all data visualizations.
- Ensure all pages are responsive (mobile-first).
