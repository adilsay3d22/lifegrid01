# One command per task (spec section 1, rule 8). Requires Docker; see README for running without it.
SCENARIO ?= normal
SEED ?= 42
POLICIES ?= A,B,C
SEEDS ?= 30
DC = docker compose
RUN = $(DC) run --rm --no-deps api

.PHONY: up down migrate seed test lint sim sim-report logs

up: .env
	$(DC) up -d --build

down:
	$(DC) down

.env:
	cp .env.example .env

migrate:
	$(DC) run --rm migrate

seed:
	$(DC) run --rm -e DATABASE_URL=postgresql+psycopg://lifegrid:$$(grep DB_OWNER_PASSWORD .env | cut -d= -f2)@db:5432/lifegrid api \
		python -m simulation seed --scenario $(SCENARIO) --seed $(SEED)

test:
	cd backend && python -m pytest
	cd frontend && npm run build

lint:
	cd backend && ruff check . && mypy app
	cd frontend && npx tsc -b

sim:
	cd backend && python -m simulation run --scenario $(SCENARIO) --policies $(POLICIES) --seeds $(SEEDS)

sim-report:
	cd backend && python -m simulation report

logs:
	$(DC) logs -f api worker beat
