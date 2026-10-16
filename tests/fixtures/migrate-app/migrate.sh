#!/bin/sh
# Tiny migration runner for the fixture: applies migrations/NNN_name.up.sql in order,
# records them in schema_migrations, and rolls back the last one with "down".
set -eu
psql -v ON_ERROR_STOP=1 -qc "create table if not exists schema_migrations (version text primary key, applied_at timestamptz default now())"
case "${1:-up}" in
  up)
    for f in $(ls /migrations/*.up.sql | sort); do
      v=$(basename "$f" .up.sql)
      if [ -z "$(psql -tAc "select 1 from schema_migrations where version = '$v'")" ]; then
        echo "applying $v"
        psql -v ON_ERROR_STOP=1 -q -1 -f "$f" -c "insert into schema_migrations (version) values ('$v')"
      fi
    done
    echo "up to date" ;;
  down)
    v=$(psql -tAc "select version from schema_migrations order by version desc limit 1")
    [ -n "$v" ] || { echo "nothing to roll back"; exit 0; }
    echo "rolling back $v"
    psql -v ON_ERROR_STOP=1 -q -1 -f "/migrations/$v.down.sql" -c "delete from schema_migrations where version = '$v'" ;;
  *) echo "usage: migrate.sh up|down" >&2; exit 2 ;;
esac
