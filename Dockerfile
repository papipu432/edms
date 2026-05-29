# syntax=docker/dockerfile:1

# --- Builder stage ---
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN uv sync --frozen --no-dev

# --- Final stage ---
FROM python:3.11-slim

# Create non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Ensure venv is on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY --chown=appuser:appgroup app/ /app/app/
COPY --chown=appuser:appgroup alembic/ /app/alembic/
COPY --chown=appuser:appgroup alembic.ini /app/alembic.ini
COPY --chown=appuser:appgroup scripts/ /app/scripts/

# Make entrypoint executable
RUN chmod +x /app/scripts/entrypoint.sh

# Create necessary directories with proper permissions
RUN mkdir -p /app/storage /app/wiki /app/data /app/logs && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')" || exit 1

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
