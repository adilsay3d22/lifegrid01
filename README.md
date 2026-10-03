# LifeGrid

Decision support for a regional blood network: one live view of stock, 7-day demand forecasts, and a nightly transfer plan a manager approves. Spec: [docs/spec.md](docs/spec.md). Built so far: phases 0–6 (setup, auth and audit, inventory and compatibility, simulator, forecasting, redistribution, requests and donor network) plus every screen in section 15, and low-stock donor appeals. All data is synthetic.

## Run with Docker

```bash
cp .env.example .env
make up            # api, worker, beat, db (PostGIS), redis, web, mailpit; migrations run first
make seed          # demo region from the `normal` scenario, seed 42
```

Web app: http://localhost:8080 · API docs: http://localhost:8000/api/v1/docs · Mailpit: http://localhost:8025

## Run without Docker (SQLite, no workers)

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"     # .venv/bin/pip on macOS/Linux
DATABASE_URL=sqlite:///./demo.db .venv/Scripts/python -m simulation seed --create-schema
scripts/dev-api.cmd        # Windows; elsewhere: DATABASE_URL=sqlite:///./demo.db CELERY_ALWAYS_EAGER=true ENV=dev .venv/bin/python -m uvicorn app.main:app --port 8000
cd ../frontend && npm install && npm run dev:live    # http://localhost:5173, proxies /api to :8000
```

`npm run dev` (without `:live`) runs the web app on its own built-in synthetic data, including the phase 6/7 screens.

## Free hosted demo

Vercel (web app + API function) + Neon (Postgres): [docs/deploy.md](docs/deploy.md).

## Demo accounts (synthetic)

All staff use password `synthetic-demo-pass`. The administrator also needs an authenticator code: add the secret `LIFEGRIDDEMOSECRETKEYAAAAAAAAAAA` to any TOTP app.

| Email | Role |
| --- | --- |
| nabila.karim@lifegrid.test | Blood bank manager |
| tanvir.rahman@lifegrid.test | Hospital transfusion lead (H-01) |
| farhana.siddiqui@lifegrid.test | Hospital transfusion lead (H-02, H-03) |
| imran.chowdhury@lifegrid.test | Donor coordinator |
| sadia.haque@lifegrid.test | Administrator (TOTP) |
| mahmud.alam@lifegrid.test | Auditor |

## Phone app (donors and requesters)

Open http://localhost:5173 (it opens `/app`; installable as an app). Seeded phone logins, any of which shows its one-time code on screen in development:

| Phone | Who |
| --- | --- |
| `+8801000000001` | Donor (O+, lives near Southfield General, eligible) |
| `+8801000009999` | Requester |
| any other number | New account: donors go through registration first |

A typical run: the requester asks for blood at a hospital → the hospital lead (`tanvir.rahman`, Southfield) confirms → stock is reserved or transfers proposed, and only the shortfall goes to donors. Or: the bank manager opens **Low stock** on the overview → **Appeal to donors** → eligible donors nearby get an SMS (mock) and an invitation → they accept and message the hospital team. Use a separate browser or private window per person: one browser holds one sign-in.

## Commands

| | |
| --- | --- |
| `make test` | backend tests (unit, integration, property) + frontend build |
| `make lint` | ruff, mypy (strict for `app/modules`), TypeScript |
| `make sim SCENARIO=normal POLICIES=A,B,C SEEDS=30` | experiments → `docs/results/runs/*.json` |
| `make sim-report` | `docs/results/report.md` and `results.csv` |
| `python -m app.modules.audit verify` | recompute the audit hash chain |
| `npm run gen:api` (frontend) | regenerate the typed API client from OpenAPI |

## Layout

`backend/app/modules/<module>/` — `models.py`, `schemas.py`, `service.py` (the only entry point for other modules), `router.py`, `rules.py` / pure algorithms (`forecasting/engine.py`, `redistribution/optimizer.py`). `backend/simulation/` — scenarios, generator, engine, runner, demo seed. `frontend/src/api/` — generated schema, live client, synthetic mock. Decisions and deviations: [docs/decisions](docs/decisions).

## Status of build phases

| Phase | State |
| --- | --- |
| 0 Setup | Done. CI deferred (decision 0004). |
| 1 Sites, users, auth | Done: password + TOTP, phone codes, rotating refresh tokens, scope checks, hash-chained audit. |
| 2 Inventory, compatibility | Done: lifecycle with locks, FEFO, import, expiry job, excursions, property tests. |
| 3 Simulator | Done: 6 scenarios, policies A–C, reproducible runs, demo seed. |
| 4 Forecasting | Done: baseline, Poisson, ETS with backtest selection; GBM deferred (decision 0003). |
| 5 Redistribution | Done: MILP optimizer + fallback, approval, dispatch, receipt; 30-seed results in docs/results. |
| 6 Requests, donors, matching | Done: registration, eligibility, waves, masked chat, outcomes, low-stock appeals (decision 0005). |
| 7–8 | Not started. Alerts and reports screens run on synthetic data. |
