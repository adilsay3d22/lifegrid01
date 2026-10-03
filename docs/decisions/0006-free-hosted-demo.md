# 0006: Free hosted demo (Vercel + Neon)

Date: 2026-10-03

- **One Vercel project:** the web app is the static build (`frontend/dist`); the API is one Python function (`api/index.py`) that serves the FastAPI app. `/api/*` rewrites to it, so the SPA and API share an origin and the refresh cookie stays `SameSite=Strict` (SEC-12).
- **Size:** the API's Linux wheels are about 560 MB with test folders; Vercel's Python limit is 500 MB. `vercel.json` excludes test folders and caches (about 350 MB measured locally). scikit-learn and uvicorn are left out of the root `requirements.txt`; the app doesn't import them.
- **Database:** Neon Postgres (the code relies on Postgres row and advisory locks). Turso/libSQL would turn those into no-ops. Migrations and the seed run once from a developer machine.
- **`ENV=demo`:** startup fails on the dev default keys; with no SMS provider, OTP codes are shown on screen. Not for real users or data.
- **Jobs without workers:** on Vercel (`VERCEL` is set) a middleware runs due jobs before a request: matching waves at most once a minute, expiry every 15 minutes. With no traffic, nothing advances; a minute-level external pinger would keep Neon awake and use up its free compute. Nightly forecasts and plans: "Run plan" in the UI.
- **Rate limits** use `x-real-ip` on Vercel (set by Vercel, not the client) and are per instance without Redis.
