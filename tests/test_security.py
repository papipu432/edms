"""Tests for the security monitoring module."""

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.models.security import SecurityAlert
from app.models.user import Role, User, UserRole
from app.services.ransomware_detector import RansomwareDetector, reset_detector


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
        username="secadmin",
        email="secadmin@edms.local",
        display_name="Security Admin",
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


@pytest.fixture
def detector(tmp_path):
    """Create a RansomwareDetector configured for testing."""
    reset_detector()
    d = RansomwareDetector(
        data_dir=str(tmp_path / "data"),
        threshold_ops_per_sec=5,
        window_seconds=2,
        quarantine_dir=str(tmp_path / "quarantine"),
    )
    yield d
    if d.is_running:
        d.stop()
    reset_detector()


# ---- Detector unit tests ----


class TestRansomwareDetectorInit:
    """Test detector initialization."""

    def test_init_defaults(self, detector):
        assert detector.threshold_ops_per_sec == 5
        assert detector.window_seconds == 2
        assert not detector.is_running

    def test_init_custom_params(self, tmp_path):
        d = RansomwareDetector(
            data_dir=str(tmp_path / "custom"),
            threshold_ops_per_sec=100,
            window_seconds=30,
            quarantine_dir=str(tmp_path / "q"),
        )
        assert d.threshold_ops_per_sec == 100
        assert d.window_seconds == 30

    def test_get_status_not_running(self, detector):
        status = detector.get_status()
        assert status["is_running"] is False
        assert status["uptime"] == 0.0
        assert status["ops_per_sec"] == 0.0

    def test_get_metrics(self, detector):
        metrics = detector.get_metrics()
        assert "ops_per_sec" in metrics
        assert "window_seconds" in metrics
        assert metrics["events_in_window"] == 0


class TestThresholdDetection:
    """Test that threshold detection works correctly."""

    def test_threshold_triggered(self, detector):
        """Simulate rapid file events and verify alert is created."""
        alerts_created = []
        detector.set_alert_callback(lambda a: alerts_created.append(a))

        # Simulate many events rapidly (exceeding threshold of 5 ops/sec in 2s window)
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/tmp/test.txt"

        # 11 events in the 2s window means >5 ops/sec
        for _ in range(11):
            detector._on_file_event(mock_event)

        assert len(alerts_created) > 0
        alert = alerts_created[0]
        assert alert["alert_type"] == "high_ops_rate"
        assert alert["severity"] == "high"
        assert "ops/sec" in alert["message"]

    def test_below_threshold_no_alert(self, detector):
        """Events below threshold should not trigger alerts."""
        alerts_created = []
        detector.set_alert_callback(lambda a: alerts_created.append(a))

        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "/tmp/test.txt"

        # Only 2 events in a 2s window = 1 op/sec, below threshold of 5
        detector._on_file_event(mock_event)
        detector._on_file_event(mock_event)

        assert len(alerts_created) == 0


class TestEntropyCalculation:
    """Test Shannon entropy calculation."""

    def test_empty_data(self):
        assert RansomwareDetector._calculate_entropy(b"") == 0.0

    def test_uniform_data(self):
        """All same bytes should have zero entropy."""
        data = b"\x00" * 1000
        assert RansomwareDetector._calculate_entropy(data) == 0.0

    def test_high_entropy_data(self):
        """Random-looking data should have high entropy."""
        import os
        data = os.urandom(1000)
        entropy = RansomwareDetector._calculate_entropy(data)
        # Random data should have entropy close to 8 (max for bytes)
        assert entropy > 7.0

    def test_low_entropy_text(self):
        """Simple repeated text has moderate entropy."""
        data = b"hello world " * 100
        entropy = RansomwareDetector._calculate_entropy(data)
        # Text has lower entropy than random bytes
        assert 2.0 < entropy < 5.0

    def test_known_input(self):
        """Test with a known simple input."""
        # "AAAB" = 3 A's, 1 B. Entropy = -(3/4 * log2(3/4) + 1/4 * log2(1/4))
        data = b"AAAB"
        entropy = RansomwareDetector._calculate_entropy(data)
        assert 0.8 < entropy < 0.9  # Should be ~0.8113


class TestQuarantine:
    """Test file quarantine functionality."""

    def test_quarantine_file(self, detector, tmp_path):
        """Test moving a file to quarantine."""
        # Create a test file
        test_file = tmp_path / "data" / "suspicious.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("suspicious content")

        result = detector._quarantine_file(str(test_file))
        assert result["status"] == "quarantined"
        assert not test_file.exists()

    def test_quarantine_nonexistent_file(self, detector):
        """Test quarantining a file that doesn't exist."""
        result = detector._quarantine_file("/nonexistent/path.txt")
        assert result["status"] == "error"


class TestDetectorStartStop:
    """Test start/stop lifecycle (mocked observer)."""

    @patch("app.services.ransomware_detector.WATCHDOG_AVAILABLE", True)
    @patch("app.services.ransomware_detector.Observer")
    def test_start_stop(self, mock_observer_class, detector):
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        result = detector.start()
        assert result["status"] == "started"
        assert detector.is_running

        result = detector.stop()
        assert result["status"] == "stopped"
        assert not detector.is_running
        mock_observer.stop.assert_called_once()

    @patch("app.services.ransomware_detector.WATCHDOG_AVAILABLE", True)
    @patch("app.services.ransomware_detector.Observer")
    def test_start_already_running(self, mock_observer_class, detector):
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        detector.start()
        result = detector.start()
        assert result["status"] == "already_running"
        detector.stop()

    def test_stop_not_running(self, detector):
        result = detector.stop()
        assert result["status"] == "not_running"

    @patch("app.services.ransomware_detector.WATCHDOG_AVAILABLE", False)
    def test_start_no_watchdog(self, detector):
        result = detector.start()
        assert result["status"] == "error"
        assert "watchdog not installed" in result["message"]


# ---- API endpoint tests ----


class TestSecurityPageAPI:
    """Test the security settings page endpoint."""

    async def test_settings_security_page(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/settings/security",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert "Security Monitoring" in resp.text

    async def test_settings_security_unauthorized(self, client: AsyncClient):
        resp = await client.get("/settings/security")
        assert resp.status_code == 401


class TestSecurityStatusAPI:
    """Test security status endpoint."""

    async def test_get_status(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/security/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "is_running" in data
        assert "ops_per_sec" in data
        assert "alerts_total" in data


class TestSecurityAlertsAPI:
    """Test security alerts endpoints."""

    async def test_get_alerts_empty(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/security/alerts",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["alerts"] == []

    async def test_acknowledge_alert(
        self, client: AsyncClient, admin_token: str, db_session
    ):
        # Create an alert in the DB
        alert = SecurityAlert(
            alert_type="high_ops_rate",
            severity="high",
            message="Test alert",
        )
        db_session.add(alert)
        await db_session.flush()
        await db_session.refresh(alert)
        alert_id = alert.id

        resp = await client.post(
            f"/api/security/alerts/{alert_id}/acknowledge",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_acknowledge_nonexistent_alert(
        self, client: AsyncClient, admin_token: str
    ):
        resp = await client.post(
            "/api/security/alerts/nonexistent-id/acknowledge",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"


class TestMonitorControlAPI:
    """Test monitor start/stop endpoints."""

    async def test_start_monitor(self, client: AsyncClient, admin_token: str):
        reset_detector()
        with patch("app.services.ransomware_detector.WATCHDOG_AVAILABLE", True), \
             patch("app.services.ransomware_detector.Observer") as mock_obs:
            mock_obs.return_value = MagicMock()
            resp = await client.post(
                "/api/security/monitor/start",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] in ("started", "error", "already_running")
        reset_detector()

    async def test_stop_monitor(self, client: AsyncClient, admin_token: str):
        reset_detector()
        resp = await client.post(
            "/api/security/monitor/stop",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("stopped", "not_running")
        reset_detector()


class TestSecurityConfigAPI:
    """Test security config endpoints."""

    async def test_get_config(self, client: AsyncClient, admin_token: str):
        reset_detector()
        resp = await client.get(
            "/api/security/config",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "threshold_ops_per_sec" in data
        assert "window_seconds" in data
        assert "monitored_dir" in data
        reset_detector()

    async def test_update_config(self, client: AsyncClient, admin_token: str):
        reset_detector()
        resp = await client.post(
            "/api/security/config",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"threshold_ops_per_sec": 100, "window_seconds": 20},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

        # Verify change persisted in detector
        resp2 = await client.get(
            "/api/security/config",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        config = resp2.json()
        assert config["threshold_ops_per_sec"] == 100
        assert config["window_seconds"] == 20
        reset_detector()
