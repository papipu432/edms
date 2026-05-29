"""Tests for the security monitoring layer."""

import time
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.user import Role, User, UserRole
from app.services.security_configs import (
    generate_auditd_rules,
    generate_falco_rules,
    generate_kms_audit_config,
    generate_suricata_rules,
)
from app.services.security_monitoring import KMSRateLimiter, MonitoringAlertProcessor


# ---- Fixtures ----


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    roles_data = [
        ("admin", "Administrator"),
        ("reviewer", "Reviewer"),
        ("editor", "Editor"),
    ]
    for code, name in roles_data:
        db_session.add(Role(code=code, name=name, description=f"{code} role", is_system=True))
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user in the test database."""
    from sqlalchemy import select

    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="monitoradmin",
        email="monitoradmin@edms.local",
        display_name="Monitor Admin",
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
async def admin_token(admin_user):
    """Create a valid JWT token for the admin user."""
    return create_access_token(data={"sub": admin_user.username})


# ---- KMS Rate Limiter Tests ----


class TestKMSRateLimiter:
    """Tests for KMS rate limiter."""

    def test_allows_calls_within_limit(self):
        """Rate limiter allows calls below the threshold."""
        limiter = KMSRateLimiter(max_calls_per_minute=5, window_seconds=60)
        ip = "192.168.1.1"

        for _ in range(5):
            assert limiter.check_rate_limit(ip) is True
            limiter.record_call(ip)

    def test_blocks_after_exceeding_threshold(self):
        """Rate limiter blocks after exceeding max calls."""
        limiter = KMSRateLimiter(max_calls_per_minute=10, window_seconds=60)
        ip = "10.0.0.1"

        # Make 10 calls (at the limit)
        for _ in range(10):
            assert limiter.check_rate_limit(ip) is True
            limiter.record_call(ip)

        # 11th call should be blocked
        assert limiter.check_rate_limit(ip) is False

    def test_different_ips_independent(self):
        """Rate limits are tracked independently per IP."""
        limiter = KMSRateLimiter(max_calls_per_minute=2, window_seconds=60)

        # Exhaust limit for IP A
        limiter.record_call("ip_a")
        limiter.record_call("ip_a")
        assert limiter.check_rate_limit("ip_a") is False

        # IP B should still be allowed
        assert limiter.check_rate_limit("ip_b") is True

    def test_get_status_returns_correct_info(self):
        """get_status returns per-IP call counts and blocked IPs."""
        limiter = KMSRateLimiter(max_calls_per_minute=3, window_seconds=60)
        limiter.record_call("10.0.0.1")
        limiter.record_call("10.0.0.1")
        limiter.record_call("10.0.0.1")

        status = limiter.get_status()
        assert status["limit"] == 3
        assert status["window_seconds"] == 60
        assert "10.0.0.1" in status["calls_per_ip"]
        assert status["calls_per_ip"]["10.0.0.1"] == 3
        assert "10.0.0.1" in status["blocked_ips"]

    def test_old_entries_expire(self):
        """Entries outside the window are cleaned up."""
        limiter = KMSRateLimiter(max_calls_per_minute=2, window_seconds=1)
        ip = "192.168.1.5"

        limiter.record_call(ip)
        limiter.record_call(ip)
        assert limiter.check_rate_limit(ip) is False

        # Wait for window to expire
        time.sleep(1.1)
        assert limiter.check_rate_limit(ip) is True


# ---- Monitoring Alert Processor Tests ----


class TestMonitoringAlertProcessor:
    """Tests for alert processing."""

    @pytest.mark.asyncio
    async def test_process_external_alert(self, db_session):
        """Processes a valid alert and creates a SecurityAlert."""
        processor = MonitoringAlertProcessor()
        alert_data = {
            "source": "falco",
            "severity": "high",
            "message": "Unexpected process detected",
            "details": {"process": "curl", "parent": "python"},
        }
        alert = await processor.process_external_alert(db_session, alert_data)
        assert alert.id is not None
        assert alert.alert_type == "external_falco"
        assert alert.severity == "high"
        assert alert.message == "Unexpected process detected"
        assert alert.details_json == {"process": "curl", "parent": "python"}

    @pytest.mark.asyncio
    async def test_process_alert_invalid_source(self, db_session):
        """Raises ValueError for invalid source."""
        processor = MonitoringAlertProcessor()
        with pytest.raises(ValueError, match="Invalid source"):
            await processor.process_external_alert(
                db_session, {"source": "invalid", "severity": "low", "message": "test"}
            )

    @pytest.mark.asyncio
    async def test_process_alert_empty_message(self, db_session):
        """Raises ValueError for empty message."""
        processor = MonitoringAlertProcessor()
        with pytest.raises(ValueError, match="Message is required"):
            await processor.process_external_alert(
                db_session, {"source": "auditd", "severity": "low", "message": ""}
            )

    def test_get_monitoring_status(self):
        """Returns status for all 4 monitoring layers."""
        processor = MonitoringAlertProcessor()
        status = processor.get_monitoring_status()
        assert "file_integrity" in status
        assert "process_monitoring" in status
        assert "kms_audit" in status
        assert "network" in status
        assert status["file_integrity"]["tool"] == "auditd"
        assert status["process_monitoring"]["tool"] == "falco"
        assert status["network"]["tool"] == "suricata"


# ---- Config Generation Tests ----


class TestSecurityConfigs:
    """Tests for security configuration generators."""

    def test_generate_auditd_rules(self):
        """Auditd rules contain expected directives."""
        rules = generate_auditd_rules("/data")
        assert "-w /data -p wa -k dms_data" in rules
        assert "-w /data -p a -k dms_data_access" in rules
        assert "dms_rename" in rules
        assert "dms_delete" in rules
        assert "unlink" in rules

    def test_generate_auditd_rules_custom_dir(self):
        """Auditd rules use custom data directory."""
        rules = generate_auditd_rules("/mnt/storage")
        assert "/mnt/storage" in rules

    def test_generate_falco_rules(self):
        """Falco rules contain expected YAML content."""
        rules = generate_falco_rules()
        assert "rule: Unexpected Process from EDMS Worker" in rules
        assert "priority: WARNING" in rules
        assert "uvicorn" in rules
        assert "tesseract" in rules

    def test_generate_suricata_rules(self):
        """Suricata rules contain expected network rules."""
        rules = generate_suricata_rules()
        assert "C2 beacon" in rules
        assert "sid:1000001" in rules
        assert "sid:1000002" in rules
        assert ".onion" in rules

    def test_generate_kms_audit_config(self):
        """KMS audit config is valid JSON with expected structure."""
        import json

        config_str = generate_kms_audit_config()
        config = json.loads(config_str)
        assert "kms_audit" in config
        assert config["kms_audit"]["enabled"] is True
        assert len(config["kms_audit"]["alert_rules"]) >= 1


# ---- API Endpoint Tests ----


class TestMonitoringStatusEndpoint:
    """Tests for the monitoring status endpoint."""

    @pytest.mark.asyncio
    async def test_monitoring_status(self, client: AsyncClient, admin_token: str):
        """GET /api/security/monitoring/status returns all 4 layers."""
        resp = await client.get(
            "/api/security/monitoring/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "file_integrity" in data
        assert "process_monitoring" in data
        assert "kms_audit" in data
        assert "network" in data


class TestAlertIngestEndpoint:
    """Tests for the alert ingest endpoint."""

    @pytest.mark.asyncio
    async def test_ingest_valid_alert(self, client: AsyncClient, admin_token: str):
        """POST valid alert creates SecurityAlert."""
        with patch("app.api.security.settings") as mock_settings:
            mock_settings.SECURITY_MONITORING_WEBHOOK_SECRET = "test-secret"
            resp = await client.post(
                "/api/security/monitoring/alerts/ingest",
                headers={
                    "Authorization": f"Bearer {admin_token}",
                    "X-Webhook-Secret": "test-secret",
                },
                json={
                    "source": "suricata",
                    "severity": "critical",
                    "message": "Possible C2 beacon detected",
                    "details": {"src_ip": "10.0.0.5", "dst_ip": "1.2.3.4"},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "alert_id" in data

    @pytest.mark.asyncio
    async def test_ingest_invalid_source(self, client: AsyncClient, admin_token: str):
        """POST with invalid source returns 422."""
        with patch("app.api.security.settings") as mock_settings:
            mock_settings.SECURITY_MONITORING_WEBHOOK_SECRET = "test-secret"
            resp = await client.post(
                "/api/security/monitoring/alerts/ingest",
                headers={
                    "Authorization": f"Bearer {admin_token}",
                    "X-Webhook-Secret": "test-secret",
                },
                json={
                    "source": "invalid_tool",
                    "severity": "low",
                    "message": "test alert",
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ingest_missing_message(self, client: AsyncClient, admin_token: str):
        """POST with empty message returns 422."""
        with patch("app.api.security.settings") as mock_settings:
            mock_settings.SECURITY_MONITORING_WEBHOOK_SECRET = "test-secret"
            resp = await client.post(
                "/api/security/monitoring/alerts/ingest",
                headers={
                    "Authorization": f"Bearer {admin_token}",
                    "X-Webhook-Secret": "test-secret",
                },
                json={
                    "source": "auditd",
                    "severity": "low",
                    "message": "",
                },
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ingest_rejects_when_no_secret_configured(
        self, client: AsyncClient, admin_token: str
    ):
        """POST returns 403 when no webhook secret is configured."""
        with patch("app.api.security.settings") as mock_settings:
            mock_settings.SECURITY_MONITORING_WEBHOOK_SECRET = ""
            resp = await client.post(
                "/api/security/monitoring/alerts/ingest",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "source": "auditd",
                    "severity": "low",
                    "message": "test",
                },
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_ingest_rejects_invalid_secret(
        self, client: AsyncClient, admin_token: str
    ):
        """POST returns error when webhook secret doesn't match."""
        with patch("app.api.security.settings") as mock_settings:
            mock_settings.SECURITY_MONITORING_WEBHOOK_SECRET = "correct-secret"
            resp = await client.post(
                "/api/security/monitoring/alerts/ingest",
                headers={
                    "Authorization": f"Bearer {admin_token}",
                    "X-Webhook-Secret": "wrong-secret",
                },
                json={
                    "source": "auditd",
                    "severity": "low",
                    "message": "test",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"


class TestConfigEndpoint:
    """Tests for the monitoring config generation endpoint."""

    @pytest.mark.asyncio
    async def test_get_auditd_config(self, client: AsyncClient, admin_token: str):
        """GET auditd config returns rules."""
        resp = await client.get(
            "/api/security/monitoring/configs/auditd",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "dms_data" in resp.text

    @pytest.mark.asyncio
    async def test_get_falco_config(self, client: AsyncClient, admin_token: str):
        """GET falco config returns YAML-like content."""
        resp = await client.get(
            "/api/security/monitoring/configs/falco",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "rule:" in resp.text

    @pytest.mark.asyncio
    async def test_get_suricata_config(self, client: AsyncClient, admin_token: str):
        """GET suricata config returns rules."""
        resp = await client.get(
            "/api/security/monitoring/configs/suricata",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "alert" in resp.text

    @pytest.mark.asyncio
    async def test_get_kms_audit_config(self, client: AsyncClient, admin_token: str):
        """GET kms_audit config returns JSON."""
        resp = await client.get(
            "/api/security/monitoring/configs/kms_audit",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "kms_audit" in resp.text

    @pytest.mark.asyncio
    async def test_get_unknown_tool_returns_404(self, client: AsyncClient, admin_token: str):
        """GET unknown tool returns 404."""
        resp = await client.get(
            "/api/security/monitoring/configs/unknown",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


class TestKMSRateLimitStatusEndpoint:
    """Tests for the KMS rate limit status endpoint."""

    @pytest.mark.asyncio
    async def test_rate_limit_status(self, client: AsyncClient, admin_token: str):
        """GET /api/security/kms/rate-limit-status returns current state."""
        resp = await client.get(
            "/api/security/kms/rate-limit-status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "limit" in data
        assert "window_seconds" in data
        assert "blocked_ips" in data
        assert "calls_per_ip" in data


# ---- KMS rate_limited_unwrap Tests ----


class TestRateLimitedUnwrap:
    """Tests for the rate_limited_unwrap function."""

    def test_rate_limited_unwrap_blocks_when_exceeded(self):
        """rate_limited_unwrap raises KMSError when rate limit is exceeded."""
        from app.services.error_handling import KMSError
        from app.services.kms import rate_limited_unwrap
        from app.services.security_monitoring import KMSRateLimiter

        # Create a limiter with very low limit
        limiter = KMSRateLimiter(max_calls_per_minute=1, window_seconds=60)
        limiter.record_call("10.0.0.1")

        with patch(
            "app.services.security_monitoring.get_kms_rate_limiter", return_value=limiter
        ):
            with pytest.raises(KMSError, match="Rate limit exceeded"):
                rate_limited_unwrap(b"some_blob", client_ip="10.0.0.1")

    def test_rate_limited_unwrap_allows_within_limit(self):
        """rate_limited_unwrap succeeds when within limit."""
        from unittest.mock import MagicMock

        from app.services.kms import rate_limited_unwrap
        from app.services.security_monitoring import KMSRateLimiter

        limiter = KMSRateLimiter(max_calls_per_minute=10, window_seconds=60)
        mock_provider = MagicMock()
        mock_provider.unwrap_key.return_value = b"decrypted_key"

        with patch("app.services.security_monitoring.get_kms_rate_limiter", return_value=limiter):
            with patch("app.services.kms.get_kms_provider", return_value=mock_provider):
                result = rate_limited_unwrap(b"some_blob", client_ip="10.0.0.2")
                assert result == b"decrypted_key"
                mock_provider.unwrap_key.assert_called_once_with(b"some_blob")
