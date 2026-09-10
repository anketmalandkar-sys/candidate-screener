#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "Seeding demo data..."
  python -m app.seed
fi

echo "Starting API on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
