#!/usr/bin/env sh
set -eu

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:?POSTGRES_PORT is required}"
: "${PORT:=8000}"
: "${STATIC_ROOT:=/vol/static}"
: "${MEDIA_ROOT:=/vol/media}"

echo "Waiting for database at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" >/dev/null 2>&1; do
  sleep 1
done
echo "Database ready!"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static to ${STATIC_ROOT}..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
exec gunicorn backend.wsgi:application \
  --bind 0.0.0.0:"${PORT}" \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --log-level "${GUNICORN_LOG_LEVEL:-info}" \
  --access-logfile - \
  --error-logfile -
