# LifeGrid web

React 18 + TypeScript + Vite, Tailwind v4, TanStack Query, React Hook Form + Zod, Recharts, Leaflet, i18next, PWA. All section 15 screens, running on synthetic mock data (see `../docs/decisions/0001-frontend-first-with-mock-api.md`).

```bash
npm install
npm run dev      # http://localhost:5173, synthetic in-memory data
npm run dev:live # same, but phases 0-5 call the API on :8000 (Vite proxies /api)
npm run gen:api  # regenerate src/api/schema.d.ts from the backend OpenAPI schema
npm run build    # typecheck + production build
```

**Staff** (`/staff/login`): open "Demo accounts" and pick a role. Any password of 12+ characters works; any 6 digits at the authenticator step (bank manager, admin).

**Donor / requester** (`/app`): any phone number, any 6-digit code.

Append `?fail` to a URL to see error states. Data resets on reload.

Layout: `src/api` (client + mock), `src/features/<area>` (screens), `src/routes` (staff and app shells, role guards), `src/components` (UI primitives), `src/i18n/en.json` (all user-facing text).
