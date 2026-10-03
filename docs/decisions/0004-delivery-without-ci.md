# 0004: No CI or GitHub setup yet; Docker stack not exercised locally

Date: 2026-10-03

- The project owner deferred GitHub, CI (lint, type checks, tests, dependency and secret scans) and the git repository itself. `make lint` and `make test` run the same checks locally. Add the GitHub Actions workflow when the repository exists.
- The build machine has no Docker, so `docker-compose.yml`, the Dockerfiles, `infra/db-init.sh` and the Makefile targets that call Docker are written but not run. The migration was checked by rendering its PostgreSQL SQL offline (`alembic upgrade head --sql`) and by running it up, down and up again on SQLite. First `make up` on a Docker machine should be treated as the real test.
- TypeScript is pinned to 5.x because `openapi-typescript` (the OpenAPI client generator, section 10) does not support TypeScript 7 yet.
