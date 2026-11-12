#!/bin/sh
# Optional migration on startup; the API owns migrations in compose.
set -e

if [ "${EVALGATE_MIGRATE:-1}" = "1" ] && [ -n "${DATABASE_URL:-}" ]; then
    echo "running alembic upgrade head"
    alembic upgrade head
fi

exec "$@"
