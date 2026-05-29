"""Geo-fencing service for IP and country-based access control."""

import ipaddress

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.geofence import GeoFenceRule


class GeoFenceService:
    """Service for evaluating geo-fence rules."""

    def check_ip_against_cidr(self, ip: str, cidr_list: list[str]) -> bool:
        """Check if an IP address matches any CIDR range in the list."""
        try:
            ip_addr = ipaddress.ip_address(ip)
        except ValueError:
            return False

        for cidr in cidr_list:
            try:
                network = ipaddress.ip_network(cidr, strict=False)
                if ip_addr in network:
                    return True
            except ValueError:
                continue
        return False

    def get_country_from_request(self, headers: dict) -> str | None:
        """Get country code from request headers (X-Country-Code)."""
        return headers.get("x-country-code") or headers.get("X-Country-Code")

    async def evaluate_rules(
        self,
        db: AsyncSession,
        ip: str,
        country: str | None = None,
        resource_type: str | None = None,
        resource_id: int | None = None,
    ) -> tuple[bool, str | None]:
        """Evaluate geo-fence rules. Returns (allowed, reason).

        Rule priority: document > group > global.
        If no rules match, default is to allow.
        """
        query = select(GeoFenceRule).where(GeoFenceRule.enabled.is_(True))
        result = await db.execute(query)
        rules = result.scalars().all()

        if not rules:
            return True, None

        # Sort by priority: document > group > global
        scope_priority = {"document": 0, "group": 1, "global": 2}
        sorted_rules = sorted(
            rules, key=lambda r: scope_priority.get(r.scope, 3)
        )

        for rule in sorted_rules:
            # Check scope applicability
            if rule.scope == "document" and resource_type == "document":
                if rule.scope_id is not None and rule.scope_id != resource_id:
                    continue
            elif rule.scope == "group" and resource_type == "group":
                if rule.scope_id is not None and rule.scope_id != resource_id:
                    continue
            elif rule.scope != "global":
                # Skip non-matching scoped rules
                if rule.scope != "global":
                    continue

            # Check denied IP ranges
            if rule.denied_ip_ranges and self.check_ip_against_cidr(
                ip, rule.denied_ip_ranges
            ):
                return False, f"IP {ip} is in denied range (rule {rule.id})"

            # Check denied countries
            if rule.denied_countries and country:
                if country.upper() in [c.upper() for c in rule.denied_countries]:
                    return False, f"Country {country} is denied (rule {rule.id})"

            # Check allowed IP ranges (if specified, IP must be in allowed list)
            if rule.allowed_ip_ranges:
                if not self.check_ip_against_cidr(ip, rule.allowed_ip_ranges):
                    return False, f"IP {ip} is not in allowed range (rule {rule.id})"

            # Check allowed countries (if specified, country must be in list)
            if rule.allowed_countries and country:
                if country.upper() not in [c.upper() for c in rule.allowed_countries]:
                    return False, f"Country {country} is not in allowed list (rule {rule.id})"

        return True, None
