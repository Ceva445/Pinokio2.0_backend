#!/bin/sh

set -e

echo "Waiting for database..."

# optional wait (simple version)
sleep 3

echo "Running migrations..."

alembic upgrade head

echo "Starting app..."

exec uvicorn app.main:app --host 0.0.0.0 --port 8000