#!/bin/bash
set -e

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
    echo "PostgreSQL is not ready yet, retrying in 2s..."
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
