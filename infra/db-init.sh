#!/bin/sh
# Runtime role for the API and workers. Migrations run as the owner; grants are applied by migration 0001.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE lifegrid_app LOGIN PASSWORD '${APP_DB_PASSWORD}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO lifegrid_app;
GRANT USAGE ON SCHEMA public TO lifegrid_app;
CREATE EXTENSION IF NOT EXISTS postgis;
SQL
