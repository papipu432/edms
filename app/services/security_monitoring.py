"""Security monitoring service with KMS rate limiting and alert processing."""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import SecurityAlert

logger = logging.getLogger(__name__)


class KMSRateLimiter:
    """Rate limiter for KMS unwrap operations using a sliding window per IP."""

    def __init__(self, max_calls_per_minute: int = 10, window_seconds: int = 60) -> None:
        self.max_calls_per_minute = max_calls_per_minute
        self.window_seconds = window_seconds
        self._calls: dict[str, list[float]] = {}

    def _clean_old_entries(self, client_ip: str) -> None:
        """Remove entries outside the current window."""
        if client_ip not in self._calls:
            return
        cutoff = time.time() - self.window_seconds
        self._calls[client_ip] = [
            ts for ts in self._calls[client_ip] if ts > cutoff
        ]
        if not self._calls[client_ip]:
            del self._calls[client_ip]

    def check_rate_limit(self, client_ip: str) -> bool:
        """Check if a client IP is within the rate limit.

        Returns True if allowed, False if exceeded.
        """
        self._clean_old_entries(client_ip)
        calls = self._calls.get(client_ip, [])
        return len(calls) < self.max_calls_per_minute

    def record_call(self, client_ip: str) -> None:
        """Record a KMS call for the given client IP."""
        if client_ip not in self._calls:
            self._calls[client_ip] = []
        self._calls[client_ip].append(time.time())

    def get_status(self) -> dict:
        """Return current rate limit status per IP."""
        now = time.time()
        cutoff = now - self.window_seconds
        status: dict[str, int] = {}
        blocked_ips: list[str] = []

        for ip, timestamps in list(self._calls.items()):
            active = [ts for ts in timestamps if ts > cutoff]
            if active:
                status[ip] = len(active)
                if len(active) >= self.max_calls_per_minute:
                    blocked_ips.append(ip)

        return {
            "calls_per_ip": status,
            "limit": self.max_calls_per_minute,
            "window_seconds": self.window_seconds,
            "blocked_ips": blocked_ips,
        }


class MonitoringAlertProcessor:
    """Processes alerts from external monitoring tools into EDMS SecurityAlerts."""

    VALID_SOURCES = {"auditd", "falco", "suricata"}
    VALID_SEVERITIES = {"low", "medium", "high", "critical"}

    async def process_external_alert(
        self, db: AsyncSession, alert_data: dict
    ) -> SecurityAlert:
        """Validate and create a SecurityAlert from external tool data.

        Expected format:
            {
                "source": "auditd|falco|suricata",
                "severity": "low|medium|high|critical",
                "message": str,
                "details": dict
            }
        """
        source = alert_data.get("source", "")
        severity = alert_data.get("severity", "medium")
        message = alert_data.get("message", "")
        details = alert_data.get("details")

        if source not in self.VALID_SOURCES:
            raise ValueError(
                f"Invalid source: {source}. Must be one of {self.VALID_SOURCES}"
            )
        if severity not in self.VALID_SEVERITIES:
            raise ValueError(
                f"Invalid severity: {severity}. Must be one of {self.VALID_SEVERITIES}"
            )
        if not message:
            raise ValueError("Message is required")

        alert = SecurityAlert(
            alert_type=f"external_{source}",
            severity=severity,
            message=message,
            details_json=details,
            source_path=f"monitoring/{source}",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(alert)
        await db.flush()
        return alert

    def get_monitoring_status(self) -> dict:
        """Return status of each monitoring layer."""
        return {
            "file_integrity": {
                "tool": "auditd",
                "status": "configured",
            },
            "process_monitoring": {
                "tool": "falco",
                "status": "configured",
            },
            "kms_audit": {
                "tool": "kms_rate_limiter",
                "status": "configured",
            },
            "network": {
                "tool": "suricata",
                "status": "configured",
            },
        }


# Module-level singleton for KMS rate limiter
_kms_rate_limiter: KMSRateLimiter | None = None


def get_kms_rate_limiter() -> KMSRateLimiter:
    """Get or create the singleton KMSRateLimiter instance."""
    global _kms_rate_limiter
    if _kms_rate_limiter is None:
        from app.core.config import settings

        _kms_rate_limiter = KMSRateLimiter(
            max_calls_per_minute=settings.KMS_RATE_LIMIT_MAX_CALLS,
            window_seconds=settings.KMS_RATE_LIMIT_WINDOW_SECONDS,
        )
    return _kms_rate_limiter
