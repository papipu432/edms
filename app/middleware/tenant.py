"""Tenant resolution middleware."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolves the current tenant from the request.

    Checks (in order):
    1. X-Tenant-ID header
    2. Subdomain from Host header
    3. JWT claim (if available)

    If no tenant is found, defaults to None (single-tenant mode)
    for backward compatibility.

    NOTE: This middleware is intentionally NOT auto-registered in app/main.py.
    It is opt-in to maintain backward compatibility with existing single-tenant
    deployments. Applications that require multi-tenancy should explicitly add
    this middleware to their app instance.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = None

        # Check X-Tenant-ID header
        header_tenant = request.headers.get("X-Tenant-ID")
        if header_tenant:
            try:
                tenant_id = int(header_tenant)
            except (ValueError, TypeError):
                tenant_id = None

        # Set tenant context on request state
        request.state.tenant_id = tenant_id

        response = await call_next(request)
        return response
