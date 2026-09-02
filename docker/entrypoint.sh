#!/bin/sh
set -e

python - <<'PY'
import os
import sys
import time

host = os.environ.get("POSTGRES_HOST", "").strip()
if not host:
    sys.exit(0)

import psycopg

port = os.environ.get("POSTGRES_PORT", "5432")
dbname = os.environ.get("POSTGRES_DB", "rogsync")
user = os.environ.get("POSTGRES_USER", "rogsync")
password = os.environ.get("POSTGRES_PASSWORD", "rogsync")

for attempt in range(40):
    try:
        with psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=3,
        ):
            break
    except Exception as exc:
        if attempt == 39:
            raise SystemExit(f"Postgres is not ready: {exc}") from exc
        time.sleep(1)
PY

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi

exec "$@"
