"""Tests for error handling: request ID, exception handlers, rate limiter, circuit breaker."""

import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.middleware.error_handler import RequestIDMiddleware, register_exception_handlers
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.services.circuit_breaker import CircuitBreaker, CircuitState
from app.services.error_handling import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionError,
    ProcessingError,
    ValidationError,
)


# ── Helper: create a test app with error handling middleware ──────────────────


def _make_error_test_app():
    """Create a minimal FastAPI app with error handling for testing."""
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(test_app)

    @test_app.get("/raise-validation")
    async def raise_validation():
        raise ValidationError("Invalid input data")

    @test_app.get("/raise-auth")
    async def raise_auth():
        raise AuthenticationError("Invalid credentials")

    @test_app.get("/raise-permission")
    async def raise_permission():
        raise PermissionError("Access denied")

    @test_app.get("/raise-notfound")
    async def raise_notfound():
        raise NotFoundError("Document not found")

    @test_app.get("/raise-conflict")
    async def raise_conflict():
        raise ConflictError("Resource already exists")

    @test_app.get("/raise-processing")
    async def raise_processing():
        raise ProcessingError("Failed to process document")

    @test_app.get("/raise-unhandled")
    async def raise_unhandled():
        raise RuntimeError("Super secret internal error with password=abc123")

    @test_app.get("/ok")
    async def ok_endpoint():
        return {"status": "ok"}

    return test_app


# ── Request ID tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_id_header_present(client: AsyncClient):
    """All responses should include X-Request-ID header with a UUID."""
    response = await client.get("/api/documents")
    assert "X-Request-ID" in response.headers
    request_id = response.headers["X-Request-ID"]
    # Should be a valid UUID format (8-4-4-4-12 hex chars)
    parts = request_id.split("-")
    assert len(parts) == 5
    assert len(parts[0]) == 8
    assert len(parts[1]) == 4
    assert len(parts[2]) == 4
    assert len(parts[3]) == 4
    assert len(parts[4]) == 12


@pytest.mark.asyncio
async def test_request_id_unique_per_request(client: AsyncClient):
    """Each request should get a unique request ID."""
    response1 = await client.get("/api/documents")
    response2 = await client.get("/api/documents")
    id1 = response1.headers.get("X-Request-ID")
    id2 = response2.headers.get("X-Request-ID")
    assert id1 != id2


# ── Custom exception handler tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_error_returns_400():
    """ValidationError should return 400 with structured response."""
    test_app = _make_error_test_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/raise-validation")
        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert data["message"] == "Invalid input data"
        assert "timestamp" in data
        assert "request_id" in data


@pytest.mark.asyncio
async def test_authentication_error_returns_401():
    """AuthenticationError should return 401."""
    test_app = _make_error_test_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/raise-auth")
        assert response.status_code == 401
        data = response.json()
        assert data["error_code"] == "AUTHENTICATION_ERROR"


@pytest.mark.asyncio
async def test_permission_error_returns_403():
    """PermissionError should return 403."""
    test_app = _make_error_test_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/raise-permission")
        assert response.status_code == 403
        data = response.json()
        assert data["error_code"] == "PERMISSION_ERROR"


@pytest.mark.asyncio
async def test_not_found_error_returns_404():
    """NotFoundError should return 404."""
    test_app = _make_error_test_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/raise-notfound")
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_conflict_error_returns_409():
    """ConflictError should return 409."""
    test_app = _make_error_test_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/raise-conflict")
        assert response.status_code == 409
        data = response.json()
        assert data["error_code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_processing_error_returns_500():
    """ProcessingError should return 500."""
    test_app = _make_error_test_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/raise-processing")
        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == "PROCESSING_ERROR"


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500_generic():
    """Unhandled exceptions should return 500 with generic message (no internal details)."""
    test_app = _make_error_test_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/raise-unhandled")
        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == "INTERNAL_ERROR"
        assert data["message"] == "An internal server error occurred"
        # Should NOT contain internal error details
        assert "password" not in data["message"]
        assert "abc123" not in str(data)


# ── Rate limiter tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limiter_blocks_after_exceeding_limit():
    """Rate limiter should return 429 after exceeding the configured limit."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    # Create a minimal app with a very low rate limit for testing
    test_app = FastAPI()
    test_app.add_middleware(RateLimiterMiddleware, requests_per_minute=5, burst=0)

    @test_app.get("/test")
    async def test_endpoint():
        return JSONResponse(content={"ok": True})

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Make 5 requests (should all succeed)
        for i in range(5):
            resp = await ac.get("/test")
            assert resp.status_code == 200, f"Request {i+1} failed with {resp.status_code}"

        # 6th request should be rate limited
        resp = await ac.get("/test")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        data = resp.json()
        assert data["error_code"] == "RATE_LIMIT_EXCEEDED"


# ── Circuit breaker tests ─────────────────────────────────────────────────────


def test_circuit_breaker_starts_closed():
    """Circuit breaker should start in closed state."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_opens_after_threshold():
    """Circuit breaker should open after consecutive failures reach threshold."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)

    def failing_func():
        raise RuntimeError("service down")

    for _ in range(3):
        cb.call(failing_func, fallback="fallback")

    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_returns_fallback_when_open():
    """When open, circuit breaker should return fallback without calling the function."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60)

    call_count = 0

    def failing_func():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("service down")

    # Open the circuit
    cb.call(failing_func, fallback="fallback")
    cb.call(failing_func, fallback="fallback")
    assert cb.state == CircuitState.OPEN
    assert call_count == 2

    # Now calling should return fallback without invoking func
    result = cb.call(failing_func, fallback="fallback_value")
    assert result == "fallback_value"
    assert call_count == 2  # func was NOT called


def test_circuit_breaker_closes_after_recovery():
    """Circuit breaker should move to half_open after timeout and close on success."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

    def failing_func():
        raise RuntimeError("service down")

    def success_func():
        return "success"

    # Open the circuit
    cb.call(failing_func, fallback="fallback")
    cb.call(failing_func, fallback="fallback")
    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    time.sleep(1.1)

    # Should be half_open now
    assert cb.state == CircuitState.HALF_OPEN

    # Successful call should close the circuit
    result = cb.call(success_func, fallback="fallback")
    assert result == "success"
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_success_resets_failures():
    """A successful call resets the failure count."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=10)

    def failing_func():
        raise RuntimeError("service down")

    def success_func():
        return "ok"

    # 2 failures (not yet at threshold)
    cb.call(failing_func, fallback="f")
    cb.call(failing_func, fallback="f")
    assert cb.state == CircuitState.CLOSED

    # 1 success resets count
    cb.call(success_func, fallback="f")
    assert cb.state == CircuitState.CLOSED

    # Need 3 more failures to open (not 1)
    cb.call(failing_func, fallback="f")
    cb.call(failing_func, fallback="f")
    assert cb.state == CircuitState.CLOSED

    cb.call(failing_func, fallback="f")
    assert cb.state == CircuitState.OPEN
