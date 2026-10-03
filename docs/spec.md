# LifeGrid: Requirements and Architecture Specification

Oct 2, 2026 · @ADIL

LifeGrid coordinates blood stock across hospitals, blood banks and volunteer donors so units are used before they expire and shortages are filled early. This document (version 1.0) is the build specification to hand to Claude Code: what to build, how it is structured, and the order to build it in. It extends Doc.

## 1. How to use this document

Build LifeGrid phase by phase from section 18, treating every "must" in this document as a requirement and every default value as configurable.

**Instructions for the implementing agent**

1. Read sections 2, 3, 6, 8 and 18 before writing any code; use the rest as reference while building.
2. Build one phase at a time. Do not start a phase until the previous phase's exit criteria pass.
3. Use synthetic data only. Never add real names, phone numbers or medical data to seeds, fixtures or tests.
4. Keep business rules (compatibility, shelf life, eligibility) in configuration and rule tables, never hard-coded inside handlers.
5. Write tests with each feature, not after. A feature is done only when it meets the definition of done in section 17.
6. When this document is silent or ambiguous, choose the simplest option that satisfies the requirement, then record it as a short decision note in `docs/decisions/`.
7. Do not add features, services or dependencies that this document does not ask for without recording a decision note first.
8. Keep the system runnable with one command (`make up`) at the end of every phase.

**Conventions used here**

- **Must** = required for the phase it belongs to. **Should** = build if time allows. **Could** = optional.
- Requirement IDs (FR, NFR, SEC) are referenced in commit messages, tests and pull requests, for example `test_fr_inv_03_status_transitions`.
- Defaults marked "(config)" live in `backend/app/core/config.py` or the `setting` table and can change without code edits.
- Clinical defaults in section 6 are placeholders for a prototype. They must be reviewed by a qualified clinician before any real use.

## 2. Product overview

LifeGrid is a decision-support web platform that gives every site in a regional blood network one live view of stock, forecasts demand, recommends transfers before units expire, and matches verified donors when stock cannot cover a request.

**Problem in one line.** Blood is perishable and type-specific, but each hospital manages it alone, so one site discards expiring units while another rations them.

**Product scope (version 1)**

| Area | Included |
| --- | --- |
| Inventory network | Units by group, component, expiry, site and status; movements; temperature excursions |
| Forecasting | 7-day demand forecast per site, component and blood group |
| Redistribution | Nightly transfer plan with manager approval |
| Requests | Verified blood requests with hospital confirmation |
| Donor network | Registration, eligibility, deferral follow-up, request-based matching, masked contact |
| Alerts | Expiry, projected stockout, temperature, unfilled request |
| Oversight | Role-based dashboards, reports, hash-chained audit log |
| Evaluation | Simulator and experiment harness comparing policies |

**Non-goals**

- Replacing a licensed blood bank information system, laboratory system or clinical judgment.
- Testing, crossmatching, labelling or release of blood.
- Real patient data, payments to donors, or donations arranged outside a licensed facility.
- Live integration with real hospital systems in version 1.
- Native mobile apps; the donor app is a progressive web app.

**Assumptions**

- A region has 5 to 100 sites (hospitals and blood banks) with known coordinates.
- Units enter LifeGrid when a site receives them as released, labelled stock; LifeGrid does not track collection or lab testing.
- Each unit has a unique identifier (in production an ISBT 128 code; in the prototype a generated string).
- All demo and test data is synthetic and produced by the simulator.

**Constraints**

- Every transfer needs human approval; LifeGrid never moves stock on its own.
- Must run on one machine with Docker Compose for demos and grading.
- English interface in version 1, with all text in translation files so Bengali can be added later.

## 3. Users, roles and permissions

LifeGrid has seven roles; staff roles are scoped to one or more sites, and access is checked on the server for every request.

| Role | Code | Signs in with | Scope |
| --- | --- | --- | --- |
| Blood bank manager | `bank_manager` | Email and password, plus optional authenticator code | Their network region |
| Hospital transfusion lead | `hospital_lead` | Email and password | Their own site(s) |
| Donor coordinator | `donor_coordinator` | Email and password | Donors in their region |
| Donor | `donor` | Phone one-time code | Their own profile |
| Requester | `requester` | Phone one-time code | Their own requests |
| Administrator | `admin` | Email and password, plus required authenticator code | Whole system |
| Auditor | `auditor` | Email and password | Read-only, whole system |

**Permission matrix** (R = read, W = create or update, A = approve, own = only their own records, summary = totals without unit or donor detail)

| Capability | bank\_manager | hospital\_lead | donor\_coordinator | donor | requester | admin | auditor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Units and stock at own site | R W | R W |  |  |  | R | R |
| Stock at other sites | R | summary | summary |  |  | R | R |
| Forecasts | R | R (own site) | R |  |  | R | R |
| Transfer recommendations | R A | R (own site) |  |  |  | R | R |
| Execute and receive transfers | W | W (own site) |  |  |  |  | R |
| Blood requests | R | R W (own site), confirm | R |  | R W (own) | R | R |
| Donor profiles |  |  | R W (eligibility fields only) | R W (own) |  | R | R |
| Donor contact details |  |  |  | own | after donor accepts |  |  |
| Invite donors for a request |  |  | W |  |  |  |  |
| Alerts | R (region) | R (own site) | R (donor alerts) | own | own | R | R |
| Rules, thresholds, sites, users |  |  |  |  |  | R W | R |
| Audit log |  |  |  |  |  | R | R |
| Simulator and experiments |  |  |  |  |  | R W | R |

No role can read donor medical detail, because LifeGrid stores only deferral categories and dates (section 16).

## 4. Functional requirements A: stock and planning

This part covers 27 requirements for inventory, compatibility, forecasting, redistribution and alerts; each has a test-ready acceptance criterion.

**Inventory (INV)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-INV-01 | Record a unit with identifier, ABO group, Rh, component, collection date, expiry, site and status | Must | Creating a unit with a missing field or expiry before collection returns a 422 error |
| FR-INV-02 | Enforce the unit lifecycle in section 6; reject invalid transitions | Must | An `expired` unit cannot become `reserved`; the API returns 409 |
| FR-INV-03 | Write a movement row for every status or location change, with user and reason | Must | Count of movement rows equals count of successful transitions in an integration test |
| FR-INV-04 | Mark units as expired automatically at their expiry time | Must | A scheduled job moves all units past expiry to `expired` within 15 minutes |
| FR-INV-05 | Show stock per site, component and group, with counts by days to expiry (0-2, 3-7, 8+) | Must | Dashboard totals match a database count for the same filters |
| FR-INV-06 | Reserve units for a confirmed request and release them on timeout (config, default 24 h) | Should | A reservation not issued before timeout returns the unit to `available` |
| FR-INV-07 | Record a temperature excursion and place affected units in quarantine | Should | Units in an excursion become `quarantined` and are excluded from available stock |
| FR-INV-08 | Bulk import units from a CSV file with row-level validation | Should | A file with one bad row imports the good rows and reports the bad row number and reason |
| FR-INV-09 | Use first-expired, first-out (FEFO) when picking units to issue or transfer | Must | Picking from a site always selects the earliest-expiring eligible unit |

**Compatibility (CMP)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-CMP-01 | Load compatibility rules per component from rule tables (section 6) | Must | Changing a rule row changes results without a code change |
| FR-CMP-02 | Given recipient group and component, return compatible donor groups ranked by preference | Must | Exact match is always ranked first; O negative red cells are ranked last for non-O-negative recipients |
| FR-CMP-03 | Never suggest an incompatible unit anywhere in the system | Must | A property-based test over all group pairs finds no incompatible suggestion |

**Forecasting (FC)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-FC-01 | Record daily usage per site, component and group from issued units | Must | Usage for a day equals units issued that day |
| FR-FC-02 | Produce a 7-day forecast per site, component and group with point, low (p10) and high (p90) values | Must | A nightly job writes 7 rows per series with low ≤ point ≤ high |
| FR-FC-03 | Include a seasonal-naive baseline and at least one better model, chosen per series by recent error | Must | The model used and its error are stored with each forecast |
| FR-FC-04 | Report forecast accuracy (mean absolute error and interval coverage) against actual usage | Should | An accuracy page shows both metrics for the last 28 days |

**Redistribution (RD)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-RD-01 | Compute a transfer plan nightly (config, default 02:00 local time) and on demand | Must | A plan is created each night with a status and solver run time |
| FR-RD-02 | Each recommendation states from site, to site, component, group, units, reason and expected benefit | Must | All fields are present and units > 0 |
| FR-RD-03 | Only transfer units with enough shelf life left (config per component) | Must | No recommended unit expires within the minimum remaining days |
| FR-RD-04 | Require bank manager approval before execution; allow edits to the unit count | Must | An unapproved recommendation cannot be dispatched |
| FR-RD-05 | Dispatch moves picked units to `in_transit`; receipt moves them to `available` at the destination | Must | Unit location changes only on receipt |
| FR-RD-06 | Fall back to a rule-based plan if the solver exceeds its time limit (config, default 30 s) | Must | A forced timeout still returns a plan marked `fallback` |
| FR-RD-07 | Show the plan's expected effect on expiry and shortage before approval | Should | The approval screen shows projected expired and short units with and without the plan |

**Alerts (ALR)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-ALR-01 | Alert when units at a site will expire within a window (config, default 3 days for red cells, 1 day for platelets) | Must | An alert appears for the affected site and role |
| FR-ALR-02 | Alert when forecast demand exceeds stock for a group and component within 2 days | Must | A projected stockout creates one alert, not one per hour |
| FR-ALR-03 | Alert on temperature excursions | Should | An excursion record creates a critical alert |
| FR-ALR-04 | Deliver alerts in-app and by email or SMS according to user preference; acknowledge and resolve | Must | An acknowledged alert records who acknowledged it and when |

## 5. Functional requirements B: people and oversight

This part covers 32 requirements for sign-in, requests, donors, matching, audit, administration and simulation.

**Authentication (AUTH)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-AUTH-01 | Staff sign in with email and password; administrators also need an authenticator code | Must | An admin without a valid code cannot sign in |
| FR-AUTH-02 | Donors and requesters sign in with a 6-digit code sent by SMS, valid 5 minutes, at most 5 attempts | Must | A sixth wrong code locks the number for 15 minutes |
| FR-AUTH-03 | Issue short-lived access tokens (15 minutes) and rotating refresh tokens (7 days) | Must | A reused refresh token revokes the whole session |
| FR-AUTH-04 | Check role and site scope on the server for every endpoint | Must | A hospital lead calling another site's stock endpoint gets 403 |

**Blood requests (REQ)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-REQ-01 | A requester or hospital lead creates a request: patient group, component, units, hospital, urgency (`emergency`, `urgent`, `routine`), needed-by time | Must | A request without hospital or needed-by time returns 422 |
| FR-REQ-02 | A hospital lead at the named site must confirm a requester's request before any action | Must | Unconfirmed requests never trigger transfers or donor invitations |
| FR-REQ-03 | On confirmation, check network stock first and propose transfers or reservations | Must | If stock covers the request, no donor is contacted |
| FR-REQ-04 | If stock cannot cover the request, start donor matching for the shortfall | Must | Matching starts only for units still needed |
| FR-REQ-05 | Follow the request states in section 6 and show status to the requester | Must | The requester sees donors notified, accepted and units secured |
| FR-REQ-06 | Limit each requester to 3 open requests and 5 new requests per day (config) | Should | The sixth request in a day returns 429 |

**Donors (DON)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-DON-01 | Register with verified phone, blood group (self-reported or verified), coarse area (map pin rounded to about 1 km) and explicit consent | Must | Registration without consent cannot be saved |
| FR-DON-02 | Store the last donation date and enforce the cooldown in section 6 | Must | A donor inside the cooldown is never invited |
| FR-DON-03 | Let coordinators record deferrals by category with an eligible-again date | Must | A deferred donor is excluded until that date |
| FR-DON-04 | Remind a donor when they become eligible again, once, by their chosen channel | Should | Exactly one reminder is sent per eligibility date |
| FR-DON-05 | Donors set availability (`available`, `unavailable`, `travelling`), quiet hours and a maximum number of requests per month | Must | No invitation is sent during quiet hours except for emergencies the donor opted into |
| FR-DON-06 | Donors can download and delete their data | Must | Deletion removes personal fields and keeps only anonymous counts |
| FR-DON-07 | Mark a blood group as verified when a coordinator confirms it from a facility record | Should | Matching prefers verified groups when scores tie |

**Matching (MAT)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-MAT-01 | Find eligible donors by group compatibility, cooldown, deferral, availability, quiet hours and distance | Must | Every invited donor passes all filters in a test with mixed donors |
| FR-MAT-02 | Rank donors with the score in section 13 and invite in waves | Must | Wave sizes and timing follow the configured rules |
| FR-MAT-03 | Send invitations showing only blood group needed, hospital area and urgency | Must | The invitation payload contains no requester name or phone |
| FR-MAT-04 | On accept, reserve the donor for this request and open an in-app message thread; share phone numbers only if both sides opt in | Must | The requester cannot see the donor's phone before both opt in |
| FR-MAT-05 | Stop inviting once accepted donors cover the shortfall plus a margin (config, default 50%) | Must | No new wave starts after coverage is reached |
| FR-MAT-06 | Widen the radius and alert the coordinator and bank manager if no donor accepts in time | Should | An unfilled emergency request escalates after the configured wait |
| FR-MAT-07 | Record donation outcome (`donated`, `no_show`, `deferred_on_site`) to update reliability | Must | Reliability changes only from recorded outcomes |

**Audit and administration (AUD, ADM)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-AUD-01 | Write an audit event for every sensitive action (section 16) in the same transaction as the change | Must | A rolled-back change leaves no audit event |
| FR-AUD-02 | Chain audit events by hash and provide a verification command | Must | Editing any stored event makes verification fail at that event |
| FR-ADM-01 | Administrators manage sites, users, roles and site scopes | Must | Disabling a user ends their sessions within 1 minute |
| FR-ADM-02 | Administrators edit rule tables and settings, with versioning | Must | Every change stores old value, new value, user and time |
| FR-ADM-03 | Export reports (stock, wastage, transfers, requests) as CSV | Should | Exported totals match dashboard totals |

**Simulation (SIM)**

| ID | Requirement | Priority | Acceptance criterion |
| --- | --- | --- | --- |
| FR-SIM-01 | Generate a synthetic region (sites, units, demand, donors, requests, disruptions) from a seed and a scenario file | Must | The same seed and scenario produce identical data |
| FR-SIM-02 | Run policies A to D (section 14) on the same scenario and seeds | Must | One command runs all policies and writes results |
| FR-SIM-03 | Seed the demo database from a scenario so the app has realistic data | Must | `make seed` produces a working demo region |

## 6. Business rules

All rules below live in rule tables or settings so a clinician can review and change them without code changes; values marked placeholder must be confirmed against local standards before any real use.

**Red cell compatibility** (recipient → acceptable donor groups, in order of preference)

| Recipient | Acceptable donors, most preferred first |
| --- | --- |
| O− | O− |
| O+ | O+, O− |
| A− | A−, O− |
| A+ | A+, A−, O+, O− |
| B− | B−, O− |
| B+ | B+, B−, O+, O− |
| AB− | AB−, A−, B−, O− |
| AB+ | AB+, AB−, A+, A−, B+, B−, O+, O− |

**Plasma compatibility** (ABO only; AB plasma ranked last because it is scarce)

| Recipient | Acceptable donors, most preferred first |
| --- | --- |
| O | O, A, B, AB |
| A | A, AB |
| B | B, AB |
| AB | AB |

**Platelets.** Prefer ABO-identical units. Allow other ABO groups when none are available (config `platelets_allow_out_of_group`, default true). For Rh-negative recipients, prefer Rh-negative units (config `platelets_prefer_rh_match`, default true).

**Shelf life and storage** (config, common defaults)

| Component | Shelf life | Storage range | Minimum remaining life to transfer | Expiry alert window |
| --- | --- | --- | --- | --- |
| Red cells | 42 days | 2 to 6 °C | 5 days | 3 days |
| Platelets | 5 days | 20 to 24 °C, agitated | 1 day | 1 day |
| Plasma | 365 days | Frozen, at or below −18 °C | 30 days | 14 days |

**Donor eligibility** (config, placeholders)

| Rule | Default |
| --- | --- |
| Age | 18 to 60 years |
| Minimum weight | 50 kg (self-reported) |
| Cooldown after whole blood donation | 120 days, configurable by sex and country |
| Maximum invitations per donor | 2 per 30 days, unless the donor raises it |
| Deferral | Category plus eligible-again date only; no medical detail stored |

**Unit lifecycle**

&#91;embedded content: unit lifecycle · 8 states, main transitions\]

| From | To | Trigger | Who |
| --- | --- | --- | --- |
| (new) | available | Unit received at a site | hospital\_lead, bank\_manager, import |
| available | reserved | Reserved for a confirmed request | system, hospital\_lead |
| reserved | available | Reservation timeout or request cancelled | system |
| reserved | issued | Issued to a patient | hospital\_lead |
| available | in\_transit | Approved transfer dispatched | bank\_manager, hospital\_lead |
| in\_transit | available | Received at destination (location changes here) | hospital\_lead |
| available, reserved, in\_transit | quarantined | Temperature excursion recorded | system, hospital\_lead |
| quarantined | available | Excursion reviewed and cleared | bank\_manager |
| quarantined | discarded | Fails review | bank\_manager |
| available, reserved, in\_transit | expired | Expiry time passes | system |
| expired | discarded | Disposal recorded | hospital\_lead |

**Request states**

| State | Meaning | Next states |
| --- | --- | --- |
| submitted | Created, waiting for hospital confirmation | confirmed, cancelled |
| confirmed | Hospital confirmed; stock check runs | covered\_by\_stock, matching |
| covered\_by\_stock | Network stock reserved or a transfer proposed for all units | fulfilled, matching |
| matching | Donor invitations in progress for the shortfall | fulfilled, partially\_fulfilled, unfilled |
| fulfilled | All units secured | (final) |
| partially\_fulfilled | Needed-by time passed with some units secured | (final) |
| unfilled | Needed-by time passed with no units secured | (final) |
| cancelled | Withdrawn by requester or hospital | (final) |

**Donor match states:** `invited` → `accepted`, `declined` or `expired`; `accepted` → `donated`, `no_show`, `deferred_on_site` or `withdrawn`.

## 7. Non-functional requirements

Each target is measured at prototype scale: 20 sites, 50,000 units in history, 5,000 donors and 50 concurrent users.

| ID | Area | Requirement | Target and how to measure |
| --- | --- | --- | --- |
| NFR-01 | Performance | API reads for dashboards | 95% under 300 ms (Locust load test) |
| NFR-02 | Performance | Dashboard first load on a laptop | Under 2 s (Playwright timing) |
| NFR-03 | Performance | Nightly transfer plan for 20 sites | Under 60 s including the solver |
| NFR-04 | Performance | Donor matching for one request | First wave sent within 10 s of confirmation |
| NFR-05 | Correctness | A unit is never in two states or locations | Database constraints plus row locks on transitions; concurrency test passes |
| NFR-06 | Reliability | Retried writes do not duplicate effects | `Idempotency-Key` header on POST endpoints that change stock |
| NFR-07 | Availability | Inventory, requests and alerts keep working when workers are down | API stays up with workers stopped (chaos test) |
| NFR-08 | Scalability | Grow to 100 sites without redesign | Load test at 100 simulated sites meets NFR-01 |
| NFR-09 | Security | Meets section 16 | Security checklist and automated scans pass |
| NFR-10 | Privacy | Minimal personal data; deletion on request | Deletion completed within 30 days; job tested |
| NFR-11 | Auditability | Sensitive actions logged and chain verifiable | 100% of listed actions produce events; verification passes |
| NFR-12 | Usability | Donor and requester flows work on a 360 px wide phone | Core tasks in 3 taps or fewer where possible; checked in Playwright mobile view |
| NFR-13 | Accessibility | WCAG 2.1 AA basics: contrast, labels, keyboard use | axe-core scan with no serious issues |
| NFR-14 | Localization | All interface text in translation files | No hard-coded user-facing strings (lint rule) |
| NFR-15 | Reproducibility | Same seed and scenario give identical results | Test compares two runs byte for byte |
| NFR-16 | Maintainability | Typed code, linted, formatted | Ruff, mypy (strict for `modules/`), ESLint and Prettier pass in CI |
| NFR-17 | Test coverage | Rule modules (compatibility, eligibility, lifecycle, matching) | 85% line coverage or higher |
| NFR-18 | Operability | Health checks and structured logs | `/healthz`, `/readyz` endpoints; JSON logs with request ID |

## 8. System architecture

LifeGrid is a modular monolith: one FastAPI backend with clear module boundaries, Celery workers for slow or scheduled jobs, and PostgreSQL as the single source of truth.

&#91;embedded content: LifeGrid architecture · 3 clients, 6 API modules, 4 worker groups\]

The API also reads and writes PostgreSQL directly; only slow work goes through the Redis queue. Workers never call the API; they share the same Python service layer and database.

**Module boundaries**

- Each module owns its tables and exposes a Python service interface (`service.py`). Other modules call that interface, never another module's tables or models directly.
- Routers stay thin: validate input, check permissions, call a service, return a schema.
- Business rules live in services and rule tables; the optimizer and forecaster are pure functions that take data and return results, so they can be tested and simulated without a database.

**Runtime flows**

1. **Nightly plan.** Celery Beat triggers forecasting at 01:30, then redistribution at 02:00. The optimizer reads stock and forecasts, writes a `transfer_plan` with recommendations, and alerts bank managers. A manager approves; a hospital lead dispatches and the destination receives, each step changing unit states in one transaction with its audit event.
2. **Blood request.** A requester submits; a hospital lead confirms. The requests service checks network stock with compatibility rules and reserves or proposes transfers. For any shortfall it enqueues matching, which sends invitation waves through notifications until coverage is reached or the request escalates.
3. **Expiry and alerts.** Every 15 minutes a job expires overdue units, releases timed-out reservations, and evaluates alert rules.
4. **Simulation.** The simulator runs in two modes: `fast`, which calls the service layer in-process for experiments, and `api`, which drives the HTTP API to seed and demo the real system.

**Why this design**

- A modular monolith is the right size for a small team: one deployable, one database, simple local runs, and boundaries that allow a later split.
- Slow jobs (forecasting, optimization, notifications) run in workers so dashboard and donor requests stay fast.
- Inventory, requests and alerts keep working when workers are down (NFR-07).
- PostgreSQL transactions and row locks guarantee that a unit is never in two states or places (NFR-05); PostGIS handles distance queries for transfers and matching.
- Writing the audit event in the same transaction as the change makes the log complete by construction.
- The provider adapter keeps SMS and email swappable and mocked in development and tests.

## 9. Technology stack

These choices are decided; use the latest stable release of each at project start and pin exact versions in lock files.

| Layer | Choice | Why |
| --- | --- | --- |
| Backend language | Python 3.12 or later | One language for API, workers, forecasting, optimization and simulation |
| Web framework | FastAPI with Pydantic v2 | Typed validation, automatic OpenAPI docs, async support |
| Database access | SQLAlchemy 2.0 (typed ORM) and Alembic migrations | Explicit transactions and row locks; versioned schema |
| Database | PostgreSQL 16 with PostGIS 3 | ACID guarantees, constraints, distance queries |
| Queue and scheduler | Celery with Redis broker; Celery Beat for schedules | Mature, well documented, one tool for jobs and timing |
| Cache and limits | Redis 7 | Rate-limit counters, short-lived cache, idempotency keys |
| Forecasting | pandas, statsmodels, scikit-learn | Seasonal models and gradient boosting that are easy to explain |
| Optimization | Google OR-Tools (linear solver with SCIP or CBC) | Free mixed-integer solver with a Python interface |
| Auth | Argon2 password hashing (argon2-cffi), PyJWT, pyotp for authenticator codes | Standard, well-tested libraries |
| Personal-data encryption | AES-GCM via the `cryptography` package, key from environment | Field-level encryption of phone numbers |
| Frontend | React 18 with TypeScript, Vite, React Router | One app with staff and donor route trees |
| UI and data | Tailwind CSS, TanStack Query, React Hook Form with Zod | Fast styling; cached server state; typed forms |
| Maps and charts | Leaflet (react-leaflet) with OpenStreetMap tiles; Recharts | Free and lightweight |
| PWA | vite-plugin-pwa | Installable donor app without app stores |
| Translations | i18next | Bengali can be added later without code changes |
| Backend tests | pytest, pytest-asyncio, httpx, factory\_boy, Hypothesis | Unit, integration and property-based tests |
| Frontend tests | Vitest, React Testing Library, Playwright, axe-core | Component, end-to-end and accessibility tests |
| Load tests | Locust | Checks NFR-01 to NFR-04 |
| Quality | Ruff, mypy, ESLint, Prettier, pre-commit | Consistent, typed code |
| Delivery | Docker Compose, Makefile, GitHub Actions | One-command start; CI on every push |

**Not used in version 1:** microservices, Kubernetes, message brokers other than Redis, native mobile apps, and paid map or SMS services. Adding any of these needs a decision note.

## 10. Repository structure and conventions

Use one repository with a backend, a frontend and shared tooling; each backend module follows the same file layout.

```text
lifegrid/
├── CLAUDE.md                 # short build rules for the agent (from section 1)
├── README.md
├── Makefile                  # up, down, seed, test, lint, migrate, sim
├── docker-compose.yml        # api, worker, beat, db, redis, web, mailpit
├── .env.example
├── docs/
│   ├── spec.md               # this document, exported
│   └── decisions/            # one short note per decision
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py           # FastAPI app factory
│   │   ├── core/             # config, security, db session, errors, logging
│   │   ├── modules/
│   │   │   ├── auth/
│   │   │   ├── sites/
│   │   │   ├── inventory/
│   │   │   ├── compatibility/
│   │   │   ├── forecasting/
│   │   │   ├── redistribution/
│   │   │   ├── requests/
│   │   │   ├── donors/
│   │   │   ├── matching/
│   │   │   ├── alerts/
│   │   │   ├── notifications/
│   │   │   └── audit/
│   │   └── workers/          # celery_app.py, beat schedule, task wrappers
│   ├── simulation/           # generator, scenarios/, policies/, runner, metrics
│   └── tests/                # unit/, integration/, property/, load/
└── frontend/
    ├── package.json
    └── src/
        ├── api/              # generated OpenAPI client
        ├── features/         # stock, transfers, requests, donors, alerts, admin
        ├── routes/           # staff/ and app/ route trees
        ├── components/
        └── i18n/
```

**Inside each backend module:** `models.py` (tables), `schemas.py` (request and response shapes), `service.py` (business logic, the only entry point for other modules), `router.py` (HTTP endpoints), `rules.py` where the module has rules, and `tests/` beside it if preferred.

**Conventions**

- Times are stored in UTC (`timestamptz`) and shown in the site's time zone.
- Primary keys are UUIDs; public unit identifiers are separate unique strings.
- Enumerations are PostgreSQL enum types or check constraints, mirrored in Pydantic.
- Every state change goes through a service method that locks the row (`SELECT ... FOR UPDATE`), validates the transition, writes the movement and audit event, and commits once.
- Settings live in environment variables (infrastructure) and the `setting` table (business rules); never in code.
- The frontend uses a client generated from the OpenAPI schema; no hand-written fetch calls for API endpoints.
- Commits follow Conventional Commits and mention requirement IDs, for example `feat(inventory): enforce lifecycle (FR-INV-02)`.
- No secret, real personal data or production key is ever committed; `.env.example` lists every variable with a safe dummy value.

## 11. Data model

The schema has 27 tables grouped by module; the definitions below are the target for the first Alembic migrations, and column names should be kept as written.

```sql
-- Enumerations
CREATE TYPE site_type      AS ENUM ('hospital','blood_bank');
CREATE TYPE user_role      AS ENUM ('bank_manager','hospital_lead','donor_coordinator','donor','requester','admin','auditor');
CREATE TYPE abo_group      AS ENUM ('O','A','B','AB');
CREATE TYPE rh_factor      AS ENUM ('pos','neg');
CREATE TYPE component      AS ENUM ('red_cells','platelets','plasma');
CREATE TYPE unit_status    AS ENUM ('available','reserved','in_transit','quarantined','issued','expired','discarded');
CREATE TYPE urgency        AS ENUM ('emergency','urgent','routine');
CREATE TYPE request_status AS ENUM ('submitted','confirmed','covered_by_stock','matching','fulfilled','partially_fulfilled','unfilled','cancelled');
CREATE TYPE match_status   AS ENUM ('invited','accepted','declined','expired','donated','no_show','deferred_on_site','withdrawn');
CREATE TYPE availability   AS ENUM ('available','unavailable','travelling');

-- Sites and users
CREATE TABLE site (
  id uuid PRIMARY KEY, code text UNIQUE NOT NULL, name text NOT NULL,
  type site_type NOT NULL, location geography(Point,4326) NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Dhaka', active boolean NOT NULL DEFAULT true);

CREATE TABLE app_user (
  id uuid PRIMARY KEY, role user_role NOT NULL,
  email citext UNIQUE, password_hash text, totp_secret_enc bytea,
  phone_enc bytea, phone_hash text UNIQUE,          -- encrypted value + keyed hash for lookup
  active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (email IS NOT NULL OR phone_hash IS NOT NULL));

CREATE TABLE user_site (user_id uuid REFERENCES app_user, site_id uuid REFERENCES site,
  PRIMARY KEY (user_id, site_id));

-- Inventory
CREATE TABLE blood_unit (
  id uuid PRIMARY KEY, unit_code text UNIQUE NOT NULL,
  abo abo_group NOT NULL, rh rh_factor NOT NULL, component component NOT NULL,
  collected_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
  site_id uuid NOT NULL REFERENCES site, status unit_status NOT NULL DEFAULT 'available',
  reserved_for uuid,                                 -- blood_request.id when reserved
  version integer NOT NULL DEFAULT 0,                -- optimistic check in addition to row locks
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (expires_at > collected_at),
  CHECK ((status = 'reserved') = (reserved_for IS NOT NULL)));
CREATE INDEX ON blood_unit (site_id, component, abo, rh, status, expires_at);

CREATE TABLE transfer (
  id uuid PRIMARY KEY, recommendation_id uuid, from_site_id uuid NOT NULL REFERENCES site,
  to_site_id uuid NOT NULL REFERENCES site, status text NOT NULL,   -- approved, dispatched, received, cancelled
  dispatched_at timestamptz, received_at timestamptz, CHECK (from_site_id <> to_site_id));

CREATE TABLE unit_movement (
  id bigserial PRIMARY KEY, unit_id uuid NOT NULL REFERENCES blood_unit,
  from_status unit_status, to_status unit_status NOT NULL,
  from_site_id uuid REFERENCES site, to_site_id uuid REFERENCES site,
  transfer_id uuid REFERENCES transfer, actor_user_id uuid REFERENCES app_user,
  reason text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE temperature_excursion (
  id uuid PRIMARY KEY, site_id uuid REFERENCES site, transfer_id uuid REFERENCES transfer,
  component component NOT NULL, started_at timestamptz NOT NULL, ended_at timestamptz,
  min_c numeric(5,2), max_c numeric(5,2), recorded_by uuid REFERENCES app_user);

-- Forecasting and redistribution
CREATE TABLE usage_daily (
  site_id uuid REFERENCES site, day date, component component, abo abo_group, rh rh_factor,
  units_used integer NOT NULL, PRIMARY KEY (site_id, day, component, abo, rh));

CREATE TABLE forecast (
  id bigserial PRIMARY KEY, run_id uuid NOT NULL, site_id uuid REFERENCES site, day date NOT NULL,
  component component, abo abo_group, rh rh_factor,
  point numeric(8,2) NOT NULL, low numeric(8,2) NOT NULL, high numeric(8,2) NOT NULL,
  model text NOT NULL, model_version text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (low <= point AND point <= high));

CREATE TABLE transfer_plan (
  id uuid PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(), horizon_days integer NOT NULL,
  status text NOT NULL,            -- proposed, reviewed, expired
  solver_status text NOT NULL, solver_seconds numeric(8,2), is_fallback boolean NOT NULL,
  projected jsonb NOT NULL);       -- expired and short units with and without the plan

CREATE TABLE transfer_recommendation (
  id uuid PRIMARY KEY, plan_id uuid NOT NULL REFERENCES transfer_plan,
  from_site_id uuid NOT NULL REFERENCES site, to_site_id uuid NOT NULL REFERENCES site,
  component component, abo abo_group, rh rh_factor, units integer NOT NULL CHECK (units > 0),
  reason text NOT NULL, expected_benefit jsonb NOT NULL,
  status text NOT NULL,            -- proposed, approved, rejected, superseded
  decided_by uuid REFERENCES app_user, decided_at timestamptz);

-- Donors, requests and matching
CREATE TABLE donor (
  id uuid PRIMARY KEY, user_id uuid UNIQUE NOT NULL REFERENCES app_user,
  abo abo_group, rh rh_factor, group_verified boolean NOT NULL DEFAULT false,
  area geography(Point,4326) NOT NULL,              -- rounded to about 1 km before storing
  birth_year integer, sex text, weight_ok boolean,  -- only what eligibility rules need
  last_donation_on date, availability availability NOT NULL DEFAULT 'available',
  quiet_start time, quiet_end time, emergency_override boolean NOT NULL DEFAULT false,
  max_invites_30d integer NOT NULL DEFAULT 2, reliability numeric(4,3) NOT NULL DEFAULT 0.5,
  consent_version text NOT NULL, consent_at timestamptz NOT NULL, deleted_at timestamptz);
CREATE INDEX ON donor USING gist (area);

CREATE TABLE deferral (
  id uuid PRIMARY KEY, donor_id uuid NOT NULL REFERENCES donor, category text NOT NULL,
  eligible_again_on date NOT NULL, recorded_by uuid REFERENCES app_user,
  created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE blood_request (
  id uuid PRIMARY KEY, requester_id uuid NOT NULL REFERENCES app_user, site_id uuid NOT NULL REFERENCES site,
  abo abo_group NOT NULL, rh rh_factor NOT NULL, component component NOT NULL,
  units_needed integer NOT NULL CHECK (units_needed BETWEEN 1 AND 20), units_secured integer NOT NULL DEFAULT 0,
  urgency urgency NOT NULL, needed_by timestamptz NOT NULL, status request_status NOT NULL DEFAULT 'submitted',
  confirmed_by uuid REFERENCES app_user, confirmed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE donor_match (
  id uuid PRIMARY KEY, request_id uuid NOT NULL REFERENCES blood_request, donor_id uuid NOT NULL REFERENCES donor,
  wave integer NOT NULL, score numeric(5,4) NOT NULL, status match_status NOT NULL DEFAULT 'invited',
  invited_at timestamptz NOT NULL DEFAULT now(), responded_at timestamptz, outcome_at timestamptz,
  UNIQUE (request_id, donor_id));

CREATE TABLE message_thread (id uuid PRIMARY KEY, match_id uuid UNIQUE NOT NULL REFERENCES donor_match,
  donor_shares_phone boolean NOT NULL DEFAULT false, requester_shares_phone boolean NOT NULL DEFAULT false);
CREATE TABLE message (id bigserial PRIMARY KEY, thread_id uuid NOT NULL REFERENCES message_thread,
  sender_id uuid NOT NULL REFERENCES app_user, body text NOT NULL CHECK (length(body) <= 1000),
  created_at timestamptz NOT NULL DEFAULT now());

-- Alerts and notifications
CREATE TABLE alert (
  id uuid PRIMARY KEY, type text NOT NULL, severity text NOT NULL, site_id uuid REFERENCES site,
  request_id uuid REFERENCES blood_request, dedup_key text NOT NULL, payload jsonb NOT NULL,
  status text NOT NULL DEFAULT 'open', acknowledged_by uuid REFERENCES app_user, acknowledged_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX alert_open_dedup ON alert (dedup_key) WHERE status <> 'resolved';

CREATE TABLE notification (id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES app_user, channel text NOT NULL,
  template text NOT NULL, status text NOT NULL, sent_at timestamptz, error text);

-- Auth support
CREATE TABLE otp_challenge (id uuid PRIMARY KEY, phone_hash text NOT NULL, code_hash text NOT NULL,
  expires_at timestamptz NOT NULL, attempts integer NOT NULL DEFAULT 0, locked_until timestamptz);
CREATE TABLE refresh_token (id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES app_user, family_id uuid NOT NULL,
  token_hash text UNIQUE NOT NULL, expires_at timestamptz NOT NULL, revoked_at timestamptz);
CREATE TABLE idempotency_key (key text PRIMARY KEY, user_id uuid NOT NULL, response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now());

-- Rules, audit, simulation
CREATE TABLE setting (key text PRIMARY KEY, value jsonb NOT NULL, version integer NOT NULL,
  updated_by uuid REFERENCES app_user, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE setting_history (id bigserial PRIMARY KEY, key text NOT NULL, old_value jsonb, new_value jsonb NOT NULL,
  version integer NOT NULL, changed_by uuid REFERENCES app_user, changed_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE compat_rule (component component, recipient_abo abo_group, recipient_rh rh_factor,
  donor_abo abo_group, donor_rh rh_factor, rank integer NOT NULL,
  PRIMARY KEY (component, recipient_abo, recipient_rh, donor_abo, donor_rh));

CREATE TABLE audit_event (
  id bigserial PRIMARY KEY, actor_user_id uuid, action text NOT NULL, entity_type text NOT NULL,
  entity_id text NOT NULL, data jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  prev_hash bytea NOT NULL, hash bytea NOT NULL);
REVOKE UPDATE, DELETE ON audit_event FROM lifegrid_app;   -- application role can only insert and read

CREATE TABLE sim_run (id uuid PRIMARY KEY, scenario text NOT NULL, seed integer NOT NULL, policy text NOT NULL,
  started_at timestamptz NOT NULL, finished_at timestamptz, metrics jsonb);
```

**Notes.** Plasma rules ignore Rh: store them with both `pos` and `neg` rows so lookups stay uniform. `audit_event` writes must be serialized (an advisory lock) so each event reads the correct previous hash. Donor deletion clears personal columns and sets `deleted_at`; match history keeps only the donor ID.

## 12. API specification

All endpoints live under `/api/v1`, return JSON, and are described by the generated OpenAPI schema at `/api/v1/openapi.json`; the list below is the minimum set.

**Conventions**

- **Auth:** `Authorization: Bearer <access token>`; refresh tokens travel in an `HttpOnly`, `Secure`, `SameSite=Strict` cookie.
- **Errors:** RFC 9457 problem details: `{"type", "title", "status", "detail", "code"}` with stable `code` values such as `invalid_transition` or `out_of_scope`.
- **Status codes:** 200 read, 201 created, 202 accepted for queued work, 401 unauthenticated, 403 out of role or scope, 404, 409 state conflict, 422 validation, 429 rate limit.
- **Pagination:** cursor-based, `?limit=50&cursor=...`, response `{"items": [...], "next_cursor": ...}`.
- **Idempotency:** POST endpoints that change stock or send invitations accept `Idempotency-Key`; a repeat returns the first response.
- **Time:** ISO 8601 with time zone in requests and responses.

**Endpoints**

| Method | Path | Roles | Purpose |
| --- | --- | --- | --- |
| POST | /auth/login | staff | Email and password; returns tokens or an authenticator challenge |
| POST | /auth/totp | staff | Complete sign-in with an authenticator code |
| POST | /auth/otp/request | public | Send a phone code (rate limited) |
| POST | /auth/otp/verify | public | Verify a phone code; creates the account on first use |
| POST | /auth/refresh | any | Rotate tokens |
| POST | /auth/logout | any | Revoke the session |
| GET | /me | any | Current user, role and site scopes |
| GET, POST | /sites | admin (write), staff (read) | List and create sites |
| PATCH | /sites/{id} | admin | Update a site |
| GET | /stock/summary | staff | Counts by site, component, group and expiry band |
| GET | /units | bank\_manager, hospital\_lead | Filter units by site, status, group, component, expiry |
| POST | /units | bank\_manager, hospital\_lead | Receive a unit at a site |
| POST | /units/import | bank\_manager, hospital\_lead | CSV import with row-level report |
| GET | /units/{id} | staff | Unit with movement history |
| POST | /units/{id}/transition | bank\_manager, hospital\_lead | Change status with reason (issue, discard, quarantine, clear) |
| POST | /excursions | bank\_manager, hospital\_lead | Record a temperature excursion |
| GET | /compatibility | staff | Compatible donor groups for a recipient group and component |
| GET | /forecasts | staff | Forecasts by site, component and group |
| GET | /forecasts/accuracy | staff | Error and coverage for the last 28 days |
| POST | /plans | bank\_manager | Run a transfer plan now (202) |
| GET | /plans, /plans/{id} | bank\_manager, hospital\_lead | Plans with recommendations and projected effect |
| POST | /recommendations/{id}/decision | bank\_manager | Approve (optionally with fewer units) or reject |
| POST | /transfers/{id}/dispatch | bank\_manager, hospital\_lead | Pick units by FEFO and mark in transit |
| POST | /transfers/{id}/receive | hospital\_lead | Receive units at destination |
| GET, POST | /requests | requester, hospital\_lead, bank\_manager | List or create blood requests |
| GET | /requests/{id} | owner, staff in scope | Request with status and match counts |
| POST | /requests/{id}/confirm | hospital\_lead | Confirm and start stock check |
| POST | /requests/{id}/cancel | owner, hospital\_lead | Cancel |
| POST | /requests/{id}/outcome | hospital\_lead | Record units received from donors |
| GET, PUT | /donor/profile | donor | Read or update own profile and availability |
| GET | /donor/export | donor | Download own data |
| DELETE | /donor/profile | donor | Delete own data |
| GET | /donor/invitations | donor | Open invitations |
| POST | /matches/{id}/respond | donor | Accept or decline |
| POST | /matches/{id}/outcome | hospital\_lead, donor\_coordinator | Record donated, no-show or deferred on site |
| GET, POST | /matches/{id}/messages | donor, requester in that match | In-app messages |
| POST | /matches/{id}/share-phone | donor, requester in that match | Opt in to share phone number |
| GET | /donors | donor\_coordinator | Search donors (no contact details) |
| POST | /donors/{id}/deferrals | donor\_coordinator | Record a deferral |
| POST | /donors/{id}/verify-group | donor\_coordinator | Mark blood group verified |
| GET | /alerts | any (scoped) | Alerts for the caller's scope |
| POST | /alerts/{id}/ack, /alerts/{id}/resolve | staff | Acknowledge or resolve |
| GET | /reports/{name}.csv | bank\_manager, admin, auditor | Stock, wastage, transfers, requests |
| GET, POST, PATCH | /admin/users | admin | Manage users, roles and site scopes |
| GET, PUT | /admin/settings/{key} | admin | Read or change a setting (versioned) |
| GET, PUT | /admin/compat-rules | admin | Read or replace compatibility rules |
| GET | /audit | admin, auditor | Search audit events |
| GET | /audit/verify | admin, auditor | Verify the hash chain |
| GET | /healthz, /readyz | public | Liveness and readiness |

## 13. Algorithm specifications

The three algorithms are pure functions with typed inputs and outputs, so they run the same in the API, the workers and the simulator. All weights and thresholds below are config defaults.

### 13.1 Demand forecasting

**Series.** One series per site, component and blood group (8 groups for red cells and platelets, 4 ABO groups for plasma). Missing days count as zero use.

**Models, tried in order of complexity**

1. **Seasonal naive (baseline):** forecast = same weekday last week. Interval = 10th and 90th percentiles of that model's errors over the last 8 weeks.
2. **Exponential smoothing** (statsmodels `ExponentialSmoothing`, additive weekly seasonality) when the series has at least 8 weeks of history.
3. **Gradient boosting** (scikit-learn `HistGradientBoostingRegressor`) with features: day of week, week of year, holiday flag (calendar in settings), lags 1, 7 and 14, 7-day and 28-day rolling means. Train three models with quantile loss at 0.1, 0.5 and 0.9 for low, point and high.
4. **Sparse series** (28-day mean below 0.5 units a day): Poisson with mean equal to the 28-day average; low and high are its 10th and 90th percentiles.

**Selection.** Each night, backtest each eligible model on a rolling origin over the last 28 days and pick the lowest mean absolute error per series; on a tie, keep the simpler model. Store model name and version with every forecast. Enforce low ≤ point ≤ high and clip negatives to zero.

### 13.2 Redistribution optimizer

**Idea.** Decide today's transfers so that, over a short horizon (H = 3 days), as few units as possible expire unused and as little demand as possible goes unmet, at low transport cost.

**Sets and data**

- Sites s, i, j; donor group g; recipient group h; component c; day t = 0 to H − 1; expiry bucket e = days until a unit expires (units beyond the horizon share one bucket).
- I₀(s, g, c, e): available units now. D(s, h, c, t): demand = forecast point + k × (high − point), with k = 0.5.
- rank(g, h, c): compatibility rank from rule tables (no entry means incompatible). dist(i, j) in km. minLife(c) from section 6.

**Decision variables (non-negative integers):** x(i, j, g, c, e) units moved today; y(s, g, h, c, e, t) units of group g used for recipient group h; u(s, h, c, t) unmet demand; w(s, g, c, e) units expiring unused; z(i, j) = 1 if lane i → j is used.

**Objective**

```latex
\min \; \sum w_E \, w + \sum w_U(h)\, u + \sum w_M\, \text{dist}(i,j)\, x + \sum w_R\, \text{rank}(g,h,c)\, y + \sum w_L\, z
```

**Constraints**

```latex
I_1(s,g,c,e) = I_0(s,g,c,e) - \sum_j x(s,j,g,c,e) + \sum_i x(i,s,g,c,e)
```

```latex
\sum_h \sum_{t \le e} y(s,g,h,c,e,t) + w(s,g,c,e) = I_1(s,g,c,e) \quad \text{for } e < H
```

```latex
\sum_{g} \sum_{e \ge t} y(s,g,h,c,e,t) + u(s,h,c,t) = D(s,h,c,t)
```

- y = 0 where the pair is incompatible; x = 0 for buckets with e < minLife(c).
- Outgoing units cannot exceed I₀; route capacity cap(i, j) per day; x ≤ M × z(i, j); at most 3 outgoing lanes per site per day.

**Default weights:** w\_E = 1 per expired unit; w\_U = 10 per unmet unit, multiplied by 3 for O−, A−, B− and AB−; w\_M = 0.01 per unit-km; w\_R = 0.1 per rank step; w\_L = 0.5 per lane.

**Output.** Sum x over buckets into recommendations per (from, to, component, group) with the projected change in expired and unmet units. At dispatch, pick physical units by FEFO among buckets that meet minLife. Solver time limit 30 s.

**Fallback (rule-based).** For each site and group, surplus = units that will expire before projected use; deficit = projected shortfall within the horizon. Match surplus to the nearest deficit site with compatible demand, largest benefit first. Mark the plan `is_fallback = true`. This rule also serves as policy B in the simulator.

### 13.3 Donor matching

**Scope in version 1.** Donor matching covers red cell needs, met by whole blood donation at a licensed facility. Platelet and plasma requests use network stock and escalate to the coordinator.

**Eligibility filter.** Not deleted; compatible group for the patient (section 6); availability `available`; cooldown passed by the needed-by time; no active deferral; age and weight rules; fewer invitations in the last 30 days than the donor's maximum; outside quiet hours unless the request is an emergency and the donor opted in; within the current search radius.

**Score for each eligible donor (0 to 1)**

```latex
\text{score} = 0.40\,P + 0.20\,G + 0.25\,R + 0.15\,F
```

- P (proximity) = 1 − min(distance ÷ radius, 1).
- G (group fit) = 1 for an exact group match, 0.5 for a compatible substitute, so O− donors are kept for those who need them.
- R (reliability) = average of response rate (responses + 1) ÷ (invitations + 2) and completion rate (donations + 1) ÷ (acceptances + 2).
- F (fairness) = min(days since last invitation ÷ 30, 1).
- Ties: verified group first, then a seeded random order.

**Waves.** Each donor's acceptance probability p = (acceptances + 1) ÷ (invitations + 2). Invite donors in score order until the sum of p reaches the shortfall × 1.5. Wait, then send the next wave if acceptances still fall short.

| Urgency | Wait between waves | Radius steps | Waves before escalation |
| --- | --- | --- | --- |
| emergency | 10 minutes | 5, 10, 20 km | 3 |
| urgent | 30 minutes | 10, 20, 40 km | 3 |
| routine | 2 hours | 15, 30 km | 2 |

**Updates.** Response and completion counts change only from recorded outcomes. Invitations that expire count as invitations without a response.

## 14. Simulator and evaluation harness

The simulator produces all demo data and all experimental results; it steps day by day through a synthetic region and is fully reproducible from a seed.

**Scenario file** (`backend/simulation/scenarios/<name>.yaml`)

```yaml
name: normal
days: 180
warmup_days: 56            # history for forecasting; excluded from metrics
region: {sites: 12, blood_banks: 2, radius_km: 40}
site_size: {small: 0.5, medium: 0.35, large: 0.15}   # sets demand level
demand:
  model: poisson
  weekly_pattern: [1.1, 1.1, 1.0, 1.0, 1.0, 0.7, 0.6] # Mon..Sun multipliers
  group_mix: {O+: 0.35, A+: 0.28, B+: 0.20, AB+: 0.07, O-: 0.04, A-: 0.03, B-: 0.02, AB-: 0.01}  # illustrative
  spikes: {probability_per_day: 0.02, multiplier: 3, duration_days: 2}
supply:
  deliveries_per_week: 3
  fill_rate: 0.95
donors: {count: 3000, base_accept_rate: 0.3, no_show_rate: 0.15}
requests: {per_week: 6, urgency_mix: {emergency: 0.2, urgent: 0.5, routine: 0.3}}
disruptions: []            # e.g. {type: donation_drop, start: 60, days: 21, factor: 0.6}
```

The blood group mix above is illustrative only; replace it with published local figures when available.

**Day loop**

1. Generate deliveries, demand and new requests for the day.
2. Run the policy (forecasting and transfers for policies C and D).
3. Serve demand with FEFO and compatibility rules; record unmet demand.
4. Run donor matching for requests (policy D only); sample donor responses and outcomes.
5. Expire overdue units; record all metrics.

**Policies**

| Code | Policy |
| --- | --- |
| A | Independent: fixed reorder levels per site, no sharing |
| B | Rule-based sharing: the fallback heuristic in section 13.2 |
| C | LifeGrid: forecasts plus the optimizer |
| D | LifeGrid plus donor matching |

**Scenarios to ship:** `normal`, `donation_drop`, `trauma_spike`, `transport_disruption`, `bad_forecast` (forecast noise added), `large_region` (100 sites, for load).

**Metrics per run:** expired units and share of stock; shortage events and unmet units, overall and for Rh-negative groups; average unit age at issue; transfer count, unit-km and lanes used; request fill rate and median time to first accepted donor; invitations per donor (spread and maximum); solver time and fallback count.

**Commands**

```bash
make seed SCENARIO=normal SEED=42              # api mode: load a demo region into the app
make sim SCENARIO=normal POLICIES=A,B,C,D SEEDS=30   # fast mode: run experiments
make sim-report                                # tables and charts to docs/results/
```

**Outputs:** one JSON file per run with config and metrics, a combined CSV, and a Markdown report with mean and 95% interval per policy and scenario. Results also go to `sim_run` when run against a database.

**Rules:** set every random generator from the seed; never read the wall clock inside the simulator; keep the simulator independent of the HTTP layer in fast mode.

## 15. Screens

The React app has two route trees: `/staff` for staff roles on desktop, and `/app` for donors and requesters on phones. Each screen lists the requirements it serves.

**Staff (`/staff`)**

| Screen | Route | Roles | What it shows and does | Requirements |
| --- | --- | --- | --- | --- |
| Sign in | /staff/login | staff | Email, password, authenticator step | FR-AUTH-01 |
| Network overview | /staff | bank\_manager, admin | Map of sites coloured by risk; stock by group and expiry band; open alerts | FR-INV-05, FR-ALR-01, FR-ALR-02 |
| Site stock | /staff/sites/:id/stock | bank\_manager, hospital\_lead | Units table with filters; receive, import, issue, discard, quarantine | FR-INV-01 to 09 |
| Unit detail | /staff/units/:id | staff | Unit fields and movement timeline | FR-INV-03 |
| Forecasts | /staff/forecasts | staff | Forecast chart with band per series; accuracy panel | FR-FC-02, FR-FC-04 |
| Transfer plan | /staff/plans/:id | bank\_manager | Recommendations with reason and benefit; approve, edit units, reject; projected effect | FR-RD-02, 04, 07 |
| Transfers | /staff/transfers | bank\_manager, hospital\_lead | Dispatch and receive with picked unit list | FR-RD-05 |
| Requests | /staff/requests | hospital\_lead, bank\_manager | Incoming requests to confirm; status and match progress | FR-REQ-01 to 05 |
| Donors | /staff/donors | donor\_coordinator | Search without contact details; deferrals; group verification; outcomes | FR-DON-03, FR-DON-07, FR-MAT-07 |
| Alerts | /staff/alerts | staff | Alert list with acknowledge and resolve | FR-ALR-04 |
| Reports | /staff/reports | bank\_manager, admin, auditor | Wastage, transfers, requests; CSV export | FR-ADM-03 |
| Administration | /staff/admin | admin | Sites, users, roles, settings, compatibility rules | FR-ADM-01, FR-ADM-02 |
| Audit | /staff/audit | admin, auditor | Event search and chain verification | FR-AUD-01, FR-AUD-02 |

**Donor and requester app (`/app`, installable PWA)**

| Screen | Route | Roles | What it shows and does | Requirements |
| --- | --- | --- | --- | --- |
| Welcome and sign in | /app | public | Phone number, one-time code | FR-AUTH-02 |
| Donor registration | /app/register | donor | Group, area pin, eligibility questions, consent | FR-DON-01 |
| Donor home | /app/donor | donor | Eligibility status, next eligible date, availability toggle | FR-DON-02, FR-DON-05 |
| Invitations | /app/invitations | donor | Group needed, hospital area, urgency; accept or decline | FR-MAT-03, FR-MAT-04 |
| Match chat | /app/matches/:id | donor, requester | In-app messages; opt in to share phone | FR-MAT-04 |
| New request | /app/requests/new | requester | Patient group, component, units, hospital, urgency, needed by | FR-REQ-01 |
| Request status | /app/requests/:id | requester | Confirmation, stock coverage, donors notified and accepted | FR-REQ-05 |
| Privacy and data | /app/privacy | donor | Download and delete my data; consent text | FR-DON-06 |

**Interface rules:** every action that changes stock shows a confirmation with unit count; destructive actions need a reason; empty, loading and error states exist for every list; all text comes from translation files.

## 16. Security and privacy requirements

LifeGrid handles health-related personal data, so security requirements are as binding as functional ones; each has an ID that tests and reviews reference.

| ID | Requirement |
| --- | --- |
| SEC-01 | Hash staff passwords with Argon2id; minimum 12 characters; check against a common-password list |
| SEC-02 | Require authenticator codes (TOTP) for administrators; offer them to all staff |
| SEC-03 | Phone codes: 6 digits, 5-minute expiry, 5 attempts, 15-minute lockout; at most 3 code requests per number per hour |
| SEC-04 | Access tokens expire in 15 minutes; refresh tokens rotate, and reuse revokes the whole session family |
| SEC-05 | Enforce role and site scope in a shared dependency on every router; deny by default; test each endpoint for each role |
| SEC-06 | Encrypt phone numbers and authenticator secrets with AES-GCM; look up phones by a keyed hash (HMAC-SHA-256); keys come from environment variables and are never logged |
| SEC-07 | Store only data that rules need: no names for donors, no addresses, no medical detail; donor area rounded to about 1 km |
| SEC-08 | Never return donor contact details except to the matched requester after both opt in (FR-MAT-04) |
| SEC-09 | No public donor directory or search; donor endpoints require authentication and are rate limited |
| SEC-10 | Rate limit sign-in, code requests, request creation and invitations per user and per IP |
| SEC-11 | Validate every input with Pydantic schemas; use the ORM or bound parameters only, never string-built SQL |
| SEC-12 | Refresh cookie `HttpOnly`, `Secure`, `SameSite=Strict`; CORS limited to the app origin; security headers (CSP, HSTS, frame denial) |
| SEC-13 | Write audit events for: sign-in, failed sign-in, role or scope change, unit transitions, transfer decisions, request confirmation, donor contact sharing, data export or deletion, settings change, audit verification |
| SEC-14 | Redact phone numbers, tokens and message bodies from logs and error reports |
| SEC-15 | Delete donor data within 30 days of request; delete expired codes and tokens daily; keep audit events (they hold IDs, not personal data) |
| SEC-16 | Run dependency checks (pip-audit, npm audit) and a secrets scan in CI; fix high-severity findings before release |
| SEC-17 | Seeds, fixtures and screenshots contain synthetic data only |
| SEC-18 | Show plain-language consent text with a version; store version and time with each donor record |

**Safety boundaries.** LifeGrid only recommends: a person approves every transfer, a hospital confirms every request, and donations happen only at licensed facilities. No payments, rewards with cash value, or private hand-overs of blood are supported. Before any real deployment, the applicable data protection law and blood transfusion regulations must be reviewed.

## 17. Testing strategy and definition of done

Tests are written with each feature and run in CI on every push; a phase is complete only when all its tests pass on a clean checkout.

| Level | Tool | What it covers | Minimum |
| --- | --- | --- | --- |
| Unit | pytest | Rules, services, algorithms as pure functions | Every FR acceptance criterion that needs no database |
| Property-based | Hypothesis | Compatibility never suggests an incompatible unit; lifecycle never reaches an invalid state; matching never invites an ineligible donor | One property test per rule module |
| Integration | pytest with PostgreSQL and Redis in Docker | Endpoints, transactions, row locks, audit events, role checks | Each endpoint × each role (allowed and denied) |
| Concurrency | pytest with parallel requests | Two users reserving or dispatching the same unit | No unit in two states (NFR-05) |
| Algorithm | pytest with small fixed scenarios | Optimizer beats or equals the fallback on known cases; forecaster beats the seasonal baseline on simulated data | Golden-file results |
| Frontend | Vitest, React Testing Library | Forms, permission-based visibility, empty and error states | Each feature folder |
| End to end | Playwright | 5 journeys: receive and issue a unit; approve and complete a transfer; request covered by stock; request filled by a donor; donor deletes data | All pass in CI |
| Accessibility | axe-core in Playwright | Staff and app screens | No serious issues |
| Load | Locust | NFR-01 to NFR-04 at prototype scale | Targets met |
| Simulation | `make sim` with a short scenario | Reproducibility and metric output | Two runs identical |

**Fixtures.** Factories create sites, units and donors from the simulator's generators so tests and demos share realistic synthetic data. Time-dependent tests use a fixed clock.

**Definition of done for any feature**

- [ ] Requirement IDs are listed in the pull request.
- [ ] Acceptance criteria are covered by automated tests that pass.
- [ ] Role and site-scope checks have allowed and denied tests.
- [ ] Audit events are written where section 16 requires them.
- [ ] Migrations run forward from an empty database.
- [ ] Ruff, mypy, ESLint and Prettier pass.
- [ ] OpenAPI schema and frontend client are regenerated.
- [ ] User-facing text is in translation files.
- [ ] `make up` and `make test` succeed on a clean checkout.
- [ ] Any deviation from this document has a note in `docs/decisions/`.

## 18. Build plan

Build in nine phases, in order; phases 0 to 5 plus phase 8 already make a complete, defensible project, and phases 6 and 7 add the donor network and the full staff experience.

### Phase 0: Project setup

- [ ] Create the repository layout from section 10, `CLAUDE.md`, `.env.example` and `docs/decisions/`.
- [ ] Docker Compose with api, worker, beat, db (PostGIS), redis, web and Mailpit for email.
- [ ] Makefile targets: up, down, migrate, seed, test, lint, sim.
- [ ] FastAPI app factory, settings, structured logging, error format, `/healthz` and `/readyz`.
- [ ] Vite React app with routing for `/staff` and `/app`, Tailwind and i18next.
- [ ] CI: lint, type checks, tests, dependency and secret scans.

**Exit:** `make up` starts every service; CI passes on an empty feature set.

### Phase 1: Sites, users and authentication

- [ ] Tables: site, app\_user, user\_site, refresh\_token, otp\_challenge, setting, setting\_history, audit\_event.
- [ ] Staff sign-in, authenticator codes, phone codes with a mock SMS provider, token rotation.
- [ ] Role and site-scope dependency used by every router (SEC-05).
- [ ] Audit service with hash chain and verification command.
- [ ] Admin screens for sites and users.

**Exit:** FR-AUTH-01 to 04, FR-AUD-01, FR-AUD-02 and FR-ADM-01 pass; each role can sign in.

### Phase 2: Inventory and compatibility

- [ ] Tables: blood\_unit, unit\_movement, transfer, temperature\_excursion, compat\_rule; seed rule tables from section 6.
- [ ] Lifecycle service with row locks, movements and audit events.
- [ ] Receive, import, issue, discard, quarantine; FEFO picking; expiry job.
- [ ] Compatibility service and property-based tests.
- [ ] Site stock and unit detail screens; stock summary endpoint.

**Exit:** FR-INV-01 to 09 and FR-CMP-01 to 03 pass; concurrency test passes.

### Phase 3: Simulator and demo data

- [ ] Generator for region, sites, units, usage history, donors and requests from a scenario file.
- [ ] Fast mode with policy A and the metrics recorder.
- [ ] API mode for `make seed`.

**Exit:** FR-SIM-01 and FR-SIM-03 pass; two runs with the same seed are identical.

### Phase 4: Forecasting

- [ ] Usage aggregation job; models and selection from section 13.1.
- [ ] Nightly Celery Beat schedule; forecast and accuracy endpoints; forecast screen.

**Exit:** FR-FC-01 to 04 pass; the chosen models beat the seasonal baseline on the `normal` scenario.

### Phase 5: Redistribution

- [ ] Fallback heuristic (also policy B); optimizer with OR-Tools (policy C).
- [ ] Plan job, approval, dispatch and receive flows; plan and transfer screens.
- [ ] Policies A, B and C in the simulator with the metrics in section 14.

**Exit:** FR-RD-01 to 07 pass; experiment runs for A, B and C complete on `normal` with 30 seeds.

### Phase 6: Requests and donor network

- [ ] Tables: donor, deferral, blood\_request, donor\_match, message\_thread, message, notification, idempotency\_key.
- [ ] Donor registration, eligibility, availability, data export and deletion.
- [ ] Requests with confirmation and stock check; matching with waves and escalation; masked messaging.
- [ ] PWA screens for donors and requesters; donor screens for coordinators.
- [ ] Policy D in the simulator.

**Exit:** FR-REQ, FR-DON and FR-MAT requirements pass; the donor and request end-to-end journeys pass.

### Phase 7: Alerts, dashboards and reports

- [ ] Alert rules with deduplication, delivery preferences, acknowledge and resolve.
- [ ] Network overview map, reports and CSV export, audit screen.

**Exit:** FR-ALR-01 to 04 and FR-ADM-02, FR-ADM-03 pass; all screens in section 15 exist.

### Phase 8: Hardening and evaluation

- [ ] Load tests, accessibility scan and security checklist (section 16).
- [ ] All scenarios × policies × 30 seeds; ablations; `make sim-report`.
- [ ] README with setup, demo script and screenshots from synthetic data.

**Exit:** every NFR target is met or explained in a decision note; the results report is generated.

## 19. Hand-off, assumptions and open questions

Export this document to Markdown as `docs/spec.md`, add the `CLAUDE.md` below at the repository root, and start Claude Code on phase 0.

**`CLAUDE.md` starter**

```markdown
# LifeGrid: build rules
Spec: docs/spec.md (source of truth). Build phases in order (section 18).
- Finish a phase only when its exit criteria and the definition of done (section 17) pass.
- Synthetic data only. Never commit secrets or real personal data.
- Rules and thresholds live in settings and rule tables, not in code.
- Every state change: lock row, validate transition, write movement + audit event, one commit.
- Check role and site scope on every endpoint; deny by default.
- Reference requirement IDs in commits and test names.
- If the spec is unclear, pick the simplest option and add a note in docs/decisions/.
Commands: make up | make migrate | make seed | make test | make lint | make sim
```

**Assumptions made in this document**

- The default time zone is Asia/Dhaka; sites can override it.
- Clinical values (compatibility ranking, shelf life, storage ranges, eligibility, cooldown) are prototype defaults and need clinical review.
- The blood group mix in the simulator is illustrative until replaced with local figures.
- No real hospital, SMS provider or patient data is connected in version 1.

**Open questions**

- How many people are on the team, and what is the submission deadline? This decides whether phases 6 and 7 are in scope.
- Does the faculty require a formal SRS format (for example IEEE 29148 with use case diagrams and data flow diagrams) in addition to this build specification?
- Which country's eligibility and cooldown rules should be the defaults?
- Is there access to a local blood bank or published local data to calibrate the simulator?
- Is a research paper expected, or only the project report and demo?
