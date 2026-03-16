#!/bin/sh
set -e
# Run migrations before starting the app (SQLite/Postgres).
python -m alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8084}"
