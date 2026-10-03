# 0002: Backend structure and small deviations (phases 0–5)

Date: 2026-10-03

## Runs on PostgreSQL and SQLite
PostgreSQL 16 is the target (Compose). The same models also run on SQLite, so tests and a local API run without Docker. Postgres-only behaviour is written in but inert on SQLite: `SELECT … FOR UPDATE` row locks, the audit advisory lock, and the `lifegrid_app` grants that make `audit_event` insert-only. The concurrency test (NFR-05) runs only when `DATABASE_URL` points at Postgres.

## Site location: lat/lng instead of PostGIS geography
`site.lat` and `site.lng` are floats. Distances use haversine in Python, which is fine to about 100 sites (transfers). PostGIS stays in the Compose image. Switch to `geography(Point)` and `ST_Distance` when donor matching (phase 6) needs radius queries over thousands of donors.

## Columns added to the section 11 schema
- `otp_challenge.created_at`: needed for "3 code requests per number per hour" (SEC-03).
- `transfer.component, abo, rh, units`: the approved line, so dispatch can pick units without re-reading a possibly edited recommendation.
- `forecast.backtest_mae, baseline_mae`: "the model used and its error are stored with each forecast" (FR-FC-03).
- `app_user.email` is stored lower-cased with a unique index instead of `citext`.

## Roles and lifecycle
- Bank managers act as site leads for blood-bank sites (receive, quarantine, discard, receive transfers into a bank). Banks have no hospital lead.
- `reserved → issued` is the only issue path, as in section 6. Reservations arrive with requests in phase 6.
- User actions on `POST /units/{id}/transition` are `issue`, `quarantine`, `clear`, `discard`; `quarantine` and `discard` need a reason.

## API additions
- `POST /units/transition` (bulk; all-or-nothing) alongside the single-unit endpoint.
- `GET /transfers`, `GET /transfers/{id}/pick` (FEFO preview before dispatch), `GET /admin/settings`, `POST /admin/users/{id}/totp` (authenticator enrolment).
- `GET /forecasts` returns one series (28 days actual + latest 7-day forecast), which is what the screen draws.
- `POST /plans` returns `202 {queued, plan_id}`; `plan_id` is set when workers run eagerly (dev/tests).

## Demo seed runs in-process
`make seed` runs the simulator through warm-up and writes the result through the models, then runs the forecast and plan jobs. Section 14's "api mode" (driving HTTP) would need auth bootstrapping for no benefit in a demo.

## Not built yet
Idempotency keys (NFR-06) arrive with the `idempotency_key` table in phase 6. Reservation timeout (FR-INV-06) needs requests (phase 6). Alerts for excursions and plan creation (FR-ALR-03) arrive with phase 7.
