from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.scanner import (
    InsaneScanner,
    ScannerService,
    TwainScanner,
)


class TestTwainScanner:
    def test_raises_runtime_error_when_twain_not_available(self):
        """Test that TwainScanner raises RuntimeError when pytwain is not importable."""
        with patch.dict("sys.modules", {"twain": None}):
            with pytest.raises(RuntimeError, match="pytwain is not available"):
                TwainScanner()

    def test_initializes_when_twain_available(self):
        """Test that TwainScanner initializes when pytwain is available."""
        mock_twain = MagicMock()
        with patch.dict("sys.modules", {"twain": mock_twain}):
            scanner = TwainScanner()
            assert scanner._twain is mock_twain


class TestInsaneScanner:
    def test_raises_runtime_error_when_pyinsane2_not_available(self):
        """Test that InsaneScanner raises RuntimeError when pyinsane2 is not importable."""
        with patch.dict("sys.modules", {"pyinsane2": None}):
            with pytest.raises(RuntimeError, match="pyinsane2 is not available"):
                InsaneScanner()

    def test_initializes_when_pyinsane2_available(self):
        """Test that InsaneScanner initializes when pyinsane2 is available."""
        mock_pyinsane = MagicMock()
        with patch.dict("sys.modules", {"pyinsane2": mock_pyinsane}):
            scanner = InsaneScanner()
            assert scanner._pyinsane is mock_pyinsane


class TestScannerServiceAutoDetect:
    def test_returns_twain_on_windows(self):
        """Test auto-detection returns TwainScanner on Windows."""
        mock_twain = MagicMock()
        with patch("platform.system", return_value="Windows"):
            with patch.dict("sys.modules", {"twain": mock_twain}):
                backend = ScannerService._auto_detect_backend()
                assert isinstance(backend, TwainScanner)

    def test_returns_insane_on_linux(self):
        """Test auto-detection returns InsaneScanner on Linux."""
        mock_pyinsane = MagicMock()
        with patch("platform.system", return_value="Linux"):
            with patch.dict("sys.modules", {"pyinsane2": mock_pyinsane}):
                backend = ScannerService._auto_detect_backend()
                assert isinstance(backend, InsaneScanner)

    def test_returns_none_when_no_backend_available(self):
        """Test auto-detection returns None when no backends are available."""
        with patch("platform.system", return_value="Linux"):
            with patch.dict("sys.modules", {"pyinsane2": None}):
                backend = ScannerService._auto_detect_backend()
                assert backend is None

    def test_returns_none_on_windows_no_twain(self):
        """Test auto-detection returns None on Windows when pytwain unavailable."""
        with patch("platform.system", return_value="Windows"):
            with patch.dict("sys.modules", {"twain": None}):
                backend = ScannerService._auto_detect_backend()
                assert backend is None


class TestScannerServiceMethods:
    def test_list_devices_with_no_backend(self):
        """Test list_devices returns empty list when no backend is available."""
        service = ScannerService(backend=None)
        assert service.list_devices() == []

    def test_list_devices_delegates_to_backend(self):
        """Test list_devices delegates to the backend."""
        mock_backend = MagicMock()
        mock_backend.list_devices.return_value = [
            {"id": "scanner1", "name": "Test Scanner", "backend": "mock"}
        ]
        service = ScannerService(backend=mock_backend)
        result = service.list_devices()
        assert len(result) == 1
        assert result[0]["id"] == "scanner1"

    def test_scan_raises_when_no_backend(self):
        """Test scan raises RuntimeError when no backend is available."""
        service = ScannerService(backend=None)
        with pytest.raises(RuntimeError, match="No scanner backend available"):
            service.scan("device1")

    def test_scan_delegates_to_backend(self, tmp_path):
        """Test scan delegates to the backend."""
        mock_backend = MagicMock()
        mock_backend.scan.return_value = tmp_path / "scan.png"
        service = ScannerService(backend=mock_backend)
        result = service.scan("device1", dpi=600, color_mode="grayscale")
        assert result == tmp_path / "scan.png"
        mock_backend.scan.assert_called_once_with("device1", 600, "grayscale")

    def test_get_device_capabilities_with_no_backend(self):
        """Test get_device_capabilities returns empty dict when no backend."""
        service = ScannerService(backend=None)
        assert service.get_device_capabilities("device1") == {}

    def test_get_device_capabilities_delegates_to_backend(self):
        """Test get_device_capabilities delegates to the backend."""
        mock_backend = MagicMock()
        mock_backend.get_device_capabilities.return_value = {
            "dpi_range": [100, 300, 600],
            "color_modes": ["color", "grayscale"],
        }
        service = ScannerService(backend=mock_backend)
        result = service.get_device_capabilities("device1")
        assert result["dpi_range"] == [100, 300, 600]


# --- API Endpoint Tests ---


@pytest_asyncio.fixture
async def scanner_client():
    """Create a test client with a mocked scanner service."""
    import app.api.scanner as scanner_module

    original_service = scanner_module.scanner_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, scanner_module

    scanner_module.scanner_service = original_service


class TestScannerAPIEndpoints:
    @pytest.mark.asyncio
    async def test_list_devices_empty(self, scanner_client):
        """Test GET /api/scanner/devices returns empty list when no backend."""
        client, scanner_module = scanner_client
        scanner_module.scanner_service = ScannerService(backend=None)

        response = await client.get("/api/scanner/devices")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_devices_with_backend(self, scanner_client):
        """Test GET /api/scanner/devices returns devices from backend."""
        client, scanner_module = scanner_client
        mock_backend = MagicMock()
        mock_backend.list_devices.return_value = [
            {"id": "scanner1", "name": "Test Scanner", "backend": "mock"}
        ]
        scanner_module.scanner_service = ScannerService(backend=mock_backend)

        response = await client.get("/api/scanner/devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "scanner1"
        assert data[0]["name"] == "Test Scanner"
        assert data[0]["backend"] == "mock"

    @pytest.mark.asyncio
    async def test_scan_no_backend_returns_503(self, scanner_client):
        """Test POST /api/scanner/scan returns 503 when no backend."""
        client, scanner_module = scanner_client
        scanner_module.scanner_service = ScannerService(backend=None)

        response = await client.post(
            "/api/scanner/scan",
            json={"device_id": "scanner1", "dpi": 300, "color_mode": "color"},
        )
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_scan_success(self, scanner_client, tmp_path):
        """Test POST /api/scanner/scan returns scan result on success."""
        client, scanner_module = scanner_client
        mock_backend = MagicMock()
        scan_path = tmp_path / "scan.png"
        scan_path.write_bytes(b"fake image data")
        mock_backend.scan.return_value = scan_path
        scanner_module.scanner_service = ScannerService(backend=mock_backend)

        response = await client.post(
            "/api/scanner/scan",
            json={"device_id": "scanner1", "dpi": 600, "color_mode": "grayscale"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert str(scan_path) in data["file_path"]

    @pytest.mark.asyncio
    async def test_scan_failure_returns_500(self, scanner_client):
        """Test POST /api/scanner/scan returns 500 on scan failure."""
        client, scanner_module = scanner_client
        mock_backend = MagicMock()
        mock_backend.scan.side_effect = RuntimeError("Scanner jammed")
        scanner_module.scanner_service = ScannerService(backend=mock_backend)

        response = await client.post(
            "/api/scanner/scan",
            json={"device_id": "scanner1"},
        )
        assert response.status_code == 500
        assert "Scanner jammed" in response.json()["detail"]
