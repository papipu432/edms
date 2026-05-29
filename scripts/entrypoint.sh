#!/bin/bash
set -e

MAX_RETRIES=30
RETRY_COUNT=0
echo "Waiting for PostgreSQL to be ready..."
until python -c "
import asyncio, asyncpg, os
async def check():
    url = os.environ.get('DATABASE_URL', '')
    if 'postgresql' not in url and 'postgres' not in url:
        return
    # Convert async URL to plain postgres URL for asyncpg
    conn_url = url.replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(conn_url)
    await conn.close()
asyncio.run(check())
" 2>/dev/null; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "ERROR: PostgreSQL not available after $MAX_RETRIES attempts. Exiting."
        exit 1
    fi
    echo "PostgreSQL is not ready yet, retrying in 2s... (attempt $RETRY_COUNT/$MAX_RETRIES)"
    sleep 2
done
echo "PostgreSQL is ready."

echo "Running database migrations..."
python -m alembic upgrade head

echo "Starting application..."
exec gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w "${WORKERS:-4}" \
    -b 0.0.0.0:8000
