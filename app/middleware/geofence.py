"""Geo-fencing middleware for IP and country-based access control."""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.database import get_db_session
from app.models.security import SecurityAlert
from app.services.geofence import GeoFenceService

logger = logging.getLogger(__name__)


class GeoFenceMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces geo-fence rules on incoming requests."""

    def __init__(self, app):
        super().__init__(app)
        self.service = GeoFenceService()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "127.0.0.1"

    async def dispatch(self, request: Request, call_next):
        if not settings.GEO_FENCE_ENABLED:
            return await call_next(request)

        ip = self._get_client_ip(request)
        country = self.service.get_country_from_request(dict(request.headers))

        try:
            async with get_db_session() as db:
                allowed, reason = await self.service.evaluate_rules(
                    db, ip, country
                )

                if not allowed:
                    # Log security alert
                    alert = SecurityAlert(
                        alert_type="geofence_denied",
                        severity="high",
                        message=f"Geo-fence denied request from IP {ip}",
                        details_json={
                            "ip": ip,
                            "country": country,
                            "reason": reason,
                            "path": str(request.url.path),
                            "method": request.method,
                        },
                        source_path=str(request.url.path),
                    )
                    db.add(alert)
                    await db.commit()

                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "Access denied by geo-fence policy",
                            "reason": reason,
                        },
                    )
        except Exception as e:
            # If geo-fence check fails, log but allow the request through
            logger.error(f"Geo-fence check failed: {e}")

        return await call_next(request)
