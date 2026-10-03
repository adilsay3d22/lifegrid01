# 0001: Build the frontend first against an in-memory mock API

Date: 2026-10-02

## Context
The spec builds phases 0–8 in order, backend first. The project owner asked for the full UI (all section 15 screens) first, with synthetic data, so the design can be reviewed before the FastAPI backend exists.

## Decision
- `frontend/src/api/client.ts` exposes one async function per section 12 endpoint. Bodies run against `api/mock.ts`, a seeded in-memory store (resets on reload). When the backend lands, replace the bodies with the generated OpenAPI client; screens do not change.
- The mock mirrors server rules only so the UI behaves realistically (lifecycle transitions, FEFO pick, scope 403s, request limits, hash-chained audit). The server stays the authority (SEC-05). UI role guards are convenience only.
- The audit hash in the mock is FNV-1a, not SHA-256; the chain logic is the same.
- No Framer Motion: motion is CSS only (staggered reveal, skeleton shimmer, live dots), honouring `prefers-reduced-motion`. Avoids a dependency the spec does not list.
- Headings use sentence case (not Title Case) for consistency with the plain-language copy.
- Group labels (O+, AB−) use the sans font, never monospace: Geist Mono renders O like 0.

## Not built yet
Excursion recording form (FR-INV-07; quarantine action covers the state change), donor outcome recording (FR-MAT-07), editing compatibility rules in the UI (read-only matrix), unsaved-changes navigation warning, alert delivery preferences, Bengali translation file.

## Update 2026-10-03 (phases 0–5 built)
`src/api/client.ts` now chooses per function: with `VITE_API=live` (`npm run dev:live`, and the Docker web image) the phase 0–5 functions call the FastAPI backend through a client typed from the generated OpenAPI schema (`src/api/schema.d.ts`, `npm run gen:api`). Phase 6/7 lists return empty and their actions answer "arrives in a later phase". Without the flag, everything stays on the synthetic mock (`src/api/mockClient.ts`).
