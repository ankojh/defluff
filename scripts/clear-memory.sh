#!/usr/bin/env bash
set -euo pipefail

DATABASE_URL="${DATABASE_URL:-postgresql://defluff:defluff@127.0.0.1:5432/defluff}"

if ! command -v psql >/dev/null 2>&1; then
    echo "psql was not found. Install Postgres first."
    exit 1
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
do $$
begin
    if exists (select from information_schema.tables where table_name = 'consumed_items') then
        execute 'truncate table consumed_items restart identity';
    end if;
    if exists (select from information_schema.tables where table_name = 'knowledge_items') then
        execute 'truncate table knowledge_items restart identity';
    end if;
end $$;
SQL

echo "Cleared local personal-knowledge tables."
