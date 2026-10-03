# 0005: Phase 6 — requests, donor network, matching and low-stock appeals

Date: 2026-10-03

## Mobile app
The donor and requester app is the installable PWA at `/app` (spec section 2: no native apps in v1). `/` opens it, the Welcome screen offers "Install the app" when the browser supports it, and the staff and phone sign-ins link to each other. A store app later can wrap the same PWA (for example with Capacitor) without a rewrite.

## Low-stock appeals (not in the spec as a separate feature)
"If blood runs low, message donors" is built as a **donor appeal**: `GET /stock/low` lists red-cell groups whose on-hand units are below the forecast for the next `stock_alert_days` (whole units), and a bank manager or donor coordinator can start an appeal (`POST /appeals`). An appeal is a `blood_request` with `kind = "appeal"`: already confirmed, no stock check (stock is the problem), straight to matching. It reuses eligibility, waves, coverage stop, escalation, outcomes and masked chat. One open appeal per site and group. A person always starts it; nothing is broadcast automatically.

## Schema additions
- `blood_request.kind, stock_units, shortfall, wave, next_wave_at, escalated_at`: matching state lives on the request.
- `site.area`: the coarse area donors see instead of the hospital (FR-MAT-03). Missing area shows "a nearby hospital", never the name.
- `donor.area_lat, area_lng` (floats, rounded to 0.01°) instead of `geography`; `donor.reminded_for` for one reminder per eligibility date (FR-DON-04).
- `notification.payload`: template variables (never contact details).

## Behaviour choices
- Confirmation reserves compatible units at the hospital first (rank, then first-expired), then proposes transfers from other sites (nearest first) as recommendations in a plan with `status = "request"`, approved by a bank manager like any other. Only the remaining shortfall goes to donors.
- Platelet and plasma shortfalls escalate to coordinators instead of matching (spec 13.3).
- Escalation notifies coordinators and bank managers in-app; alert records arrive with phase 7.
- Reliability is recomputed from `donor_match` history only when an outcome is recorded (FR-MAT-07).
- `GET /sites` is open to any signed-in user so requesters can choose a hospital (site names and locations are not personal data).

## Development conveniences (never in production)
- With `ENV=dev` and the mock SMS provider, `POST /auth/otp/request` returns `dev_code` and the app shows it, since no SMS is sent.
- `scripts/dev-api.cmd` sets `CELERY_ALWAYS_EAGER=true`; in that mode the API runs the minute jobs (matching waves, request closing) in-process because there is no Celery beat without Docker.
- The refresh cookie is per browser, so one browser holds one signed-in person. Test a donor and a staff member in separate browsers or private windows.

## Not built yet
Idempotency keys (NFR-06), alert records and delivery preferences (phase 7), email channel.
