#!/bin/sh
# Runs once on first database init (docker-entrypoint-initdb.d). Creates the RLS-restricted runtime role.
# The owner (POSTGRES_USER) runs migrations, seed and the outbox relay; the API connects only as vla_app.
set -eu
: "${POSTGRES_APP_PASSWORD:?POSTGRES_APP_PASSWORD is required}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v app_password="$POSTGRES_APP_PASSWORD" <<'SQL'
CREATE ROLE vla_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
SQL
