"""Tests for geo-fencing features."""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.geofence import GeoFenceRule
from app.models.user import Role, User, UserRole
from app.services.geofence import GeoFenceService


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    admin_role = Role(code="admin", name="Administrator", description="Admin role", is_system=True)
    viewer_role = Role(code="viewer", name="Viewer", description="Viewer role", is_system=True)
    db_session.add(admin_role)
    db_session.add(viewer_role)
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="geofence_admin",
        email="geofence_admin@edms.local",
        display_name="Geofence Admin",
        hashed_password=hash_password("admin"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=admin_role.id)
    seeded_db.add(user_role)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def regular_user(seeded_db):
    """Create a non-admin user."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.code == "viewer"))
    viewer_role = result.scalar_one()

    user = User(
        username="geofence_viewer",
        email="geofence_viewer@edms.local",
        display_name="Geofence Viewer",
        hashed_password=hash_password("viewer"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=viewer_role.id)
    seeded_db.add(user_role)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user):
    return create_access_token(data={"sub": admin_user.username})


@pytest_asyncio.fixture
async def viewer_token(regular_user):
    return create_access_token(data={"sub": regular_user.username})


class TestGeoFenceServiceCIDR:
    """Test CIDR checking logic."""

    def test_ip_in_cidr_range(self):
        service = GeoFenceService()
        assert service.check_ip_against_cidr("192.168.1.100", ["192.168.1.0/24"]) is True

    def test_ip_not_in_cidr_range(self):
        service = GeoFenceService()
        assert service.check_ip_against_cidr("10.0.0.1", ["192.168.1.0/24"]) is False

    def test_ip_in_multiple_ranges(self):
        service = GeoFenceService()
        assert service.check_ip_against_cidr(
            "10.0.0.1", ["192.168.1.0/24", "10.0.0.0/8"]
        ) is True

    def test_exact_ip_match(self):
        service = GeoFenceService()
        assert service.check_ip_against_cidr("192.168.1.1", ["192.168.1.1/32"]) is True

    def test_invalid_ip_returns_false(self):
        service = GeoFenceService()
        assert service.check_ip_against_cidr("invalid", ["192.168.1.0/24"]) is False

    def test_invalid_cidr_skipped(self):
        service = GeoFenceService()
        assert service.check_ip_against_cidr(
            "192.168.1.1", ["invalid_cidr", "192.168.1.0/24"]
        ) is True

    def test_empty_cidr_list(self):
        service = GeoFenceService()
        assert service.check_ip_against_cidr("192.168.1.1", []) is False


class TestGeoFenceServiceCountry:
    """Test country extraction from headers."""

    def test_country_from_header(self):
        service = GeoFenceService()
        headers = {"x-country-code": "US"}
        assert service.get_country_from_request(headers) == "US"

    def test_no_country_header(self):
        service = GeoFenceService()
        headers = {}
        assert service.get_country_from_request(headers) is None


class TestGeoFenceServiceRuleEvaluation:
    """Test rule evaluation logic."""

    async def test_no_rules_default_allow(self, db_session):
        service = GeoFenceService()
        allowed, reason = await service.evaluate_rules(db_session, "192.168.1.1")
        assert allowed is True
        assert reason is None

    async def test_denied_ip_range(self, db_session):
        service = GeoFenceService()
        rule = GeoFenceRule(
            scope="global",
            denied_ip_ranges=["10.0.0.0/8"],
            enabled=True,
        )
        db_session.add(rule)
        await db_session.flush()

        allowed, reason = await service.evaluate_rules(db_session, "10.0.0.1")
        assert allowed is False
        assert "denied range" in reason

    async def test_allowed_ip_range_blocks_others(self, db_session):
        service = GeoFenceService()
        rule = GeoFenceRule(
            scope="global",
            allowed_ip_ranges=["192.168.1.0/24"],
            enabled=True,
        )
        db_session.add(rule)
        await db_session.flush()

        # IP not in allowed range should be denied
        allowed, reason = await service.evaluate_rules(db_session, "10.0.0.1")
        assert allowed is False
        assert "not in allowed range" in reason

        # IP in allowed range should pass
        allowed, reason = await service.evaluate_rules(db_session, "192.168.1.50")
        assert allowed is True

    async def test_denied_country(self, db_session):
        service = GeoFenceService()
        rule = GeoFenceRule(
            scope="global",
            denied_countries=["CN", "RU"],
            enabled=True,
        )
        db_session.add(rule)
        await db_session.flush()

        allowed, reason = await service.evaluate_rules(db_session, "1.2.3.4", country="CN")
        assert allowed is False
        assert "denied" in reason

    async def test_allowed_country_blocks_others(self, db_session):
        service = GeoFenceService()
        rule = GeoFenceRule(
            scope="global",
            allowed_countries=["US", "GB"],
            enabled=True,
        )
        db_session.add(rule)
        await db_session.flush()

        allowed, reason = await service.evaluate_rules(db_session, "1.2.3.4", country="JP")
        assert allowed is False
        assert "not in allowed list" in reason

    async def test_disabled_rule_ignored(self, db_session):
        service = GeoFenceService()
        rule = GeoFenceRule(
            scope="global",
            denied_ip_ranges=["0.0.0.0/0"],
            enabled=False,
        )
        db_session.add(rule)
        await db_session.flush()

        allowed, reason = await service.evaluate_rules(db_session, "10.0.0.1")
        assert allowed is True


class TestGeoFenceAPI:
    """Test geo-fence CRUD API."""

    async def test_create_rule(self, client: AsyncClient, admin_token, seeded_db):
        resp = await client.post(
            "/api/geofence/rules",
            json={
                "scope": "global",
                "denied_ip_ranges": ["10.0.0.0/8"],
                "denied_countries": ["CN"],
                "action": "deny",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scope"] == "global"
        assert data["denied_ip_ranges"] == ["10.0.0.0/8"]
        assert data["denied_countries"] == ["CN"]

    async def test_list_rules(self, client: AsyncClient, admin_token, seeded_db):
        # Create a rule
        await client.post(
            "/api/geofence/rules",
            json={"scope": "global", "denied_ip_ranges": ["10.0.0.0/8"]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        resp = await client.get(
            "/api/geofence/rules",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    async def test_update_rule(self, client: AsyncClient, admin_token, seeded_db):
        # Create a rule
        create_resp = await client.post(
            "/api/geofence/rules",
            json={"scope": "global", "denied_ip_ranges": ["10.0.0.0/8"]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        rule_id = create_resp.json()["id"]

        # Update it
        resp = await client.put(
            f"/api/geofence/rules/{rule_id}",
            json={"denied_ip_ranges": ["172.16.0.0/12"], "enabled": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["denied_ip_ranges"] == ["172.16.0.0/12"]
        assert data["enabled"] is False

    async def test_delete_rule(self, client: AsyncClient, admin_token, seeded_db):
        # Create a rule
        create_resp = await client.post(
            "/api/geofence/rules",
            json={"scope": "global", "denied_ip_ranges": ["10.0.0.0/8"]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        rule_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/geofence/rules/{rule_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

        # Verify deleted
        resp = await client.get(
            "/api/geofence/rules",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        ids = [r["id"] for r in resp.json()]
        assert rule_id not in ids

    async def test_delete_nonexistent_rule(self, client: AsyncClient, admin_token, seeded_db):
        resp = await client.delete(
            "/api/geofence/rules/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    async def test_invalid_scope(self, client: AsyncClient, admin_token, seeded_db):
        resp = await client.post(
            "/api/geofence/rules",
            json={"scope": "invalid_scope"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400


class TestGeoFenceAdminOnly:
    """Test that geo-fence endpoints require admin role."""

    async def test_create_rule_non_admin(self, client: AsyncClient, viewer_token, seeded_db):
        resp = await client.post(
            "/api/geofence/rules",
            json={"scope": "global"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    async def test_list_rules_non_admin(self, client: AsyncClient, viewer_token, seeded_db):
        resp = await client.get(
            "/api/geofence/rules",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated(self, client: AsyncClient, seeded_db):
        resp = await client.get("/api/geofence/rules")
        assert resp.status_code == 401


class TestGeoFenceMiddleware:
    """Test geo-fence middleware behavior (disabled by default)."""

    async def test_middleware_disabled_by_default(self, client: AsyncClient, seeded_db):
        """When GEO_FENCE_ENABLED=False, requests pass through."""
        # Health endpoint or any endpoint should work without geo-fence blocking
        resp = await client.get("/api/geofence/rules")
        # Should get 401 (auth required) not 403 (geo-fence blocked)
        assert resp.status_code == 401
