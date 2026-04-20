# FreeRelay Dashboard

The administrative and analytics interface for FreeRelay users.

## Features
- **ROI Tracking**: Real-time visualization of Actual Spend vs Baseline Cost.
- **API Key Management**: Self-serve creation and revocation of access tokens.
- **Reliability Metrics**: Overview of provider fallbacks and success rates.

## Getting Started

1. **Install Dependencies**:
   ```bash
   npm install
   ```

2. **Configure Environment**:
   Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_URL`.

3. **Run Development Server**:
   ```bash
   npm run dev
   ```

4. **Access Dashboard**:
   Open [http://localhost:3000](http://localhost:3000) in your browser.

## Tech Stack
- **Framework**: Next.js (App Router)
- **UI Components**: Shadcn UI & Tailwind CSS
- **Charts**: Recharts
- **Icons**: Lucide React
