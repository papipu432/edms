"""Circuit breaker pattern for external service calls."""

import logging
import time
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker that tracks consecutive failures and opens the circuit.

    When open, calls return the provided fallback value without invoking the function.
    After recovery_timeout seconds, the circuit moves to half_open and allows one trial call.
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None

    def reset(self) -> None:
        """Reset circuit breaker state. Useful for testing."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    @property
    def state(self) -> CircuitState:
        """Return current circuit state, checking for recovery timeout."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def record_success(self) -> None:
        """Record a successful call. Resets failure count and closes circuit."""
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call. Opens circuit if threshold is reached."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker opened after %d consecutive failures",
                self._failure_count,
            )

    def call(self, func: Callable, *args: Any, fallback: Any = None, **kwargs: Any) -> Any:
        """Execute func with circuit breaker protection.

        If the circuit is open, returns fallback without calling func.
        If half_open, allows one trial call.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            logger.info("Circuit breaker is open, returning fallback")
            return fallback

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            logger.error("Circuit breaker recorded failure: %s", e)
            return fallback


# Global circuit breaker instance for LLM services
llm_circuit_breaker = CircuitBreaker()
