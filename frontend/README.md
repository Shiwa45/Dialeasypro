# DialEasypro — Admin CRM Frontend

React + TypeScript + Vite frontend for the DialEasypro admin CRM.
Connects to the TeleCRM Django backend.

## Quick Start

```bash
npm install
npm run dev        # → http://localhost:3000
npm run build      # Production build
```

## Environment Variables

Create `.env.local`:
```
VITE_API_BASE_URL=http://localhost:8000   # Your backend URL (empty = same origin)
```

In production, deploy at `{tenant}.yourdomain.com` so API calls go to the same origin.

## Pages & URLs

| Route | Page | Auth |
|-------|------|------|
| `/login` | Login | Public |
| `/dashboard` | Dashboard + KPIs | Admin |
| `/leads` | Lead list (table + kanban) | Admin |
| `/leads/:id` | Lead detail (calls, notes, WhatsApp, follow-ups) | Admin |
| `/leads/import` | CSV/XLSX bulk import | Admin |
| `/calls` | Call log with stats | Admin |
| `/agents` | Agent management | Admin |
| `/communications` | WhatsApp templates + send | Admin |
| `/campaigns` | Bulk WhatsApp/Email/SMS campaigns | Admin |
| `/reports` | Agent performance, lead sources, call analytics, funnel | Admin |
| `/integrations` | IndiaMART, Meta, Google Ads, webhooks | Admin |
| `/settings` | Custom fields, dispositions, teams, billing | Admin |
| `/profile` | Agent self-profile | Admin |

## API Endpoints Used

All calls hit `/api/v1/...` (proxied to Django backend in dev via `vite.config.ts`).

- `POST /api/v1/auth/login/` — JWT login
- `GET/PATCH /api/v1/auth/me/` — Profile
- `GET/POST /api/v1/auth/agents/` — Agent management
- `GET/POST /api/v1/leads/` — Lead CRUD
- `GET /api/v1/leads/stats/` — Dashboard KPIs
- `GET /api/v1/leads/pipeline/` — Kanban board
- `GET /api/v1/leads/export/` — CSV export
- `POST /api/v1/leads/import/` — File import
- `GET/POST /api/v1/calls/` — Call log
- `POST /api/v1/calls/click-to-call/` — Click-to-call
- `GET/POST /api/v1/comms/whatsapp/templates/` — Templates
- `POST /api/v1/comms/whatsapp/send/` — Single WhatsApp
- `POST /api/v1/comms/sms/send/` — Single SMS
- `GET/POST /api/v1/comms/campaigns/` — Bulk campaigns
- `GET /api/v1/reports/agent-performance/` — Reports
- `GET /api/v1/integrations/configs/` — Integration config
- `GET /api/v1/integrations/logs/` — Webhook logs

## Tech Stack

- **React 18** + TypeScript
- **Vite** — build tooling
- **React Router v6** — client-side routing
- **TanStack Query v5** — server state + caching
- **Axios** — HTTP client with JWT refresh interceptor
- **Zustand** — auth state (persisted to localStorage)
- **Recharts** — charts and analytics
- **Tailwind CSS** — utility classes
- **Space Grotesk** + **DM Sans** — typography

## Design System

Neobrutalist theme: heavy black borders (`2px solid #000`), offset box shadows (`5px 5px 0 #000`), yellow accent (`#ffe17c`), dark sidebar (`#171e19`).
