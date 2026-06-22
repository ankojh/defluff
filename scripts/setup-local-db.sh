#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${DB_NAME:-defluff}"
DB_USER="${DB_USER:-defluff}"
DB_PASSWORD="${DB_PASSWORD:-defluff}"
DATABASE_URL="${DATABASE_URL:-postgresql://$DB_USER:$DB_PASSWORD@127.0.0.1:5432/$DB_NAME}"

if ! command -v psql >/dev/null 2>&1; then
    echo "psql was not found. Install Postgres first."
    exit 1
fi

psql postgres -v ON_ERROR_STOP=1 \
    -v db_name="$DB_NAME" \
    -v db_user="$DB_USER" \
    -v db_password="$DB_PASSWORD" <<'SQL'
select format('create role %I login password %L', :'db_user', :'db_password')
where not exists (select 1 from pg_roles where rolname = :'db_user')\gexec

select format('alter role %I login password %L', :'db_user', :'db_password')\gexec

select format('create database %I owner %I', :'db_name', :'db_user')
where not exists (select 1 from pg_database where datname = :'db_name')\gexec
SQL

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$ROOT_DIR/backend/sql/schema.sql"

echo "Local database is ready: $DATABASE_URL"
