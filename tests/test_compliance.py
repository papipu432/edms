"""Tests for compliance reporting features."""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.audit import DocumentAuditLog
from app.models.compliance import ComplianceReport
from app.models.document import Document
from app.models.encryption import EncryptionKey
from app.models.group import Group
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState, LifecycleType
from app.models.user import Permission, Role, RolePermission, User, UserRole


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles and permissions into the test database."""
    admin_role = Role(code="admin", name="Administrator", description="Admin role", is_system=True)
    viewer_role = Role(code="viewer", name="Viewer", description="Viewer role", is_system=True)
    db_session.add(admin_role)
    db_session.add(viewer_role)
    await db_session.flush()

    # Add permissions
    perm = Permission(resource="reports", action="read")
    db_session.add(perm)
    await db_session.flush()

    rp = RolePermission(role_id=admin_role.id, permission_id=perm.id)
    db_session.add(rp)
    await db_session.flush()

    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="compliance_admin",
        email="compliance_admin@edms.local",
        display_name="Compliance Admin",
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
        username="compliance_viewer",
        email="compliance_viewer@edms.local",
        display_name="Compliance Viewer",
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


@pytest_asyncio.fixture
async def sample_data(seeded_db, admin_user):
    """Create sample data for report generation."""
    # Create a group
    group = Group(name="Test Group", description="Test")
    seeded_db.add(group)
    await seeded_db.flush()
    await seeded_db.refresh(group)

    # Create a document
    doc = Document(
        group_id=group.id,
        original_filename="test.pdf",
        storage_path="/tmp/test.pdf",
        file_type="application/pdf",
        file_size=1024,
    )
    seeded_db.add(doc)
    await seeded_db.flush()
    await seeded_db.refresh(doc)

    # Create audit log
    audit = DocumentAuditLog(
        document_id=doc.id,
        action="view",
        actor_id=admin_user.id,
        actor_username=admin_user.username,
    )
    seeded_db.add(audit)

    # Create encryption key
    key = EncryptionKey(
        key_type="dek",
        key_id_hex="abc123def456",
        is_active=True,
    )
    seeded_db.add(key)

    # Create lifecycle entry
    lifecycle = DocumentLifecycle(
        document_id=doc.id,
        lifecycle_type=LifecycleType.expiring,
        state=DocumentLifecycleState.expired,
    )
    seeded_db.add(lifecycle)
    await seeded_db.flush()

    return {"group": group, "document": doc}


class TestComplianceReportGeneration:
    """Test compliance report generation."""

    async def test_generate_access_log_report(self, client: AsyncClient, admin_token, sample_data):
        resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "access_log"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_type"] == "access_log"
        assert "data" in data
        assert data["data"]["report_type"] == "access_log"
        assert "entries" in data["data"]

    async def test_generate_encryption_status_report(self, client: AsyncClient, admin_token, sample_data):
        resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "encryption_status"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_type"] == "encryption_status"
        assert "total_documents" in data["data"]
        assert "active_keys" in data["data"]

    async def test_generate_retention_compliance_report(self, client: AsyncClient, admin_token, sample_data):
        resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "retention_compliance"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_type"] == "retention_compliance"
        assert "expired_documents" in data["data"]
        assert data["data"]["expired_documents"] >= 1

    async def test_generate_permission_audit_report(self, client: AsyncClient, admin_token, sample_data):
        resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "permission_audit"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_type"] == "permission_audit"
        assert "entries" in data["data"]
        assert data["data"]["total_users_with_roles"] >= 1

    async def test_invalid_report_type(self, client: AsyncClient, admin_token, seeded_db):
        resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "invalid_type"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    async def test_report_with_date_range(self, client: AsyncClient, admin_token, sample_data):
        resp = await client.post(
            "/api/compliance/reports",
            json={
                "report_type": "access_log",
                "start_date": "2020-01-01T00:00:00",
                "end_date": "2030-12-31T23:59:59",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200


class TestComplianceReportList:
    """Test listing and retrieving reports."""

    async def test_list_reports(self, client: AsyncClient, admin_token, sample_data):
        # Generate a report first
        await client.post(
            "/api/compliance/reports",
            json={"report_type": "encryption_status"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        resp = await client.get(
            "/api/compliance/reports",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["report_type"] == "encryption_status"

    async def test_get_specific_report(self, client: AsyncClient, admin_token, sample_data):
        # Generate a report
        create_resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "access_log"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        report_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/compliance/reports/{report_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == report_id

    async def test_get_nonexistent_report(self, client: AsyncClient, admin_token, seeded_db):
        resp = await client.get(
            "/api/compliance/reports/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


class TestComplianceCSVExport:
    """Test CSV export."""

    async def test_export_csv(self, client: AsyncClient, admin_token, sample_data):
        # Generate a report
        create_resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "encryption_status"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        report_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/compliance/reports/{report_id}/export?format=csv",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        content = resp.text
        assert "metric" in content
        assert "total_documents" in content

    async def test_export_access_log_csv(self, client: AsyncClient, admin_token, sample_data):
        create_resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "access_log"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        report_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/compliance/reports/{report_id}/export?format=csv",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "actor_username" in resp.text

    async def test_export_permission_audit_csv(self, client: AsyncClient, admin_token, sample_data):
        create_resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "permission_audit"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        report_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/compliance/reports/{report_id}/export?format=csv",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "username" in resp.text


class TestComplianceAdminOnly:
    """Test that endpoints require admin role."""

    async def test_generate_report_non_admin(self, client: AsyncClient, viewer_token, seeded_db):
        resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "access_log"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    async def test_list_reports_non_admin(self, client: AsyncClient, viewer_token, seeded_db):
        resp = await client.get(
            "/api/compliance/reports",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403

    async def test_unauthenticated_access(self, client: AsyncClient, seeded_db):
        resp = await client.post(
            "/api/compliance/reports",
            json={"report_type": "access_log"},
        )
        assert resp.status_code == 401
