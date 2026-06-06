#!/bin/bash
set -e

echo "⏳ Waiting for PostgreSQL..."
until pg_isready -h "$DB_HOST" -p "${DB_PORT:-5432}" -U "$DB_USER" -q; do
  sleep 1
done
echo "✅ PostgreSQL ready"

echo "⏳ Waiting for Redis..."
REDIS_CLI_ARGS="-h \"$REDIS_HOST\" -p \"${REDIS_PORT:-6379}\""
if [ -n "$REDIS_PASSWORD" ]; then
  REDIS_CLI_ARGS="$REDIS_CLI_ARGS -a \"$REDIS_PASSWORD\""
fi
until eval "redis-cli $REDIS_CLI_ARGS ping" | grep -q PONG; do
  sleep 1
done
echo "✅ Redis ready"

# Run shared schema migrations (public schema only)
python manage.py migrate_schemas --shared --noinput

# Collect static files
python manage.py collectstatic --noinput --clear

# Create public tenant if it doesn't exist
python manage.py create_public_tenant --domain="${BASE_DOMAIN:-telecrm.in}" || true

echo "✅ Startup complete"
exec "$@"
