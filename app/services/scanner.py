import logging
import platform
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class ScannerBackend(ABC):
    """Abstract base class for scanner backends."""

    @abstractmethod
    def list_devices(self) -> list[dict]:
        """List available scanner devices."""
        ...

    @abstractmethod
    def scan(self, device_id: str, dpi: int = 300, color_mode: str = "color") -> Path:
        """Scan a document and return path to the scanned image."""
        ...

    @abstractmethod
    def get_device_capabilities(self, device_id: str) -> dict:
        """Get capabilities of a specific device."""
        ...


class TwainScanner(ScannerBackend):
    """Windows scanner backend using pytwain (Fujitsu and other TWAIN scanners)."""

    def __init__(self):
        try:
            import twain

            self._twain = twain
        except ImportError:
            raise RuntimeError("pytwain is not available (Windows only)")

    def list_devices(self) -> list[dict]:
        """List available TWAIN scanner devices."""
        try:
            sm = self._twain.SourceManager(0)
            sources = sm.GetSourceList()
            devices = []
            for name in sources:
                devices.append({
                    "id": name,
                    "name": name,
                    "backend": "twain",
                })
            sm.close()
            return devices
        except Exception as e:
            logger.error("Failed to list TWAIN devices: %s", e)
            return []

    def scan(self, device_id: str, dpi: int = 300, color_mode: str = "color") -> Path:
        """Scan a document using a TWAIN device."""
        try:
            sm = self._twain.SourceManager(0)
            source = sm.OpenSource(device_id)
            source.SetCapability(
                self._twain.ICAP_XRESOLUTION,
                self._twain.TWTY_FIX32,
                float(dpi),
            )
            source.SetCapability(
                self._twain.ICAP_YRESOLUTION,
                self._twain.TWTY_FIX32,
                float(dpi),
            )
            source.RequestAcquire(0, 0)
            rv = source.XferImageNatively()
            if rv:
                handle, _ = rv
                tmp_dir = Path(tempfile.mkdtemp())
                output_path = tmp_dir / "scan.bmp"
                self._twain.DIBToBMFile(handle, str(output_path))
                self._twain.GlobalHandleFree(handle)
                source.close()
                sm.close()
                return output_path
            source.close()
            sm.close()
            raise RuntimeError("No image data received from scanner")
        except Exception as e:
            logger.error("TWAIN scan failed: %s", e)
            raise RuntimeError(f"Scan failed: {e}") from e

    def get_device_capabilities(self, device_id: str) -> dict:
        """Get capabilities of a TWAIN device."""
        try:
            sm = self._twain.SourceManager(0)
            source = sm.OpenSource(device_id)
            capabilities = {
                "dpi_range": [100, 200, 300, 600],
                "color_modes": ["color", "grayscale", "bw"],
                "backend": "twain",
            }
            source.close()
            sm.close()
            return capabilities
        except Exception as e:
            logger.error("Failed to get TWAIN device capabilities: %s", e)
            return {}


class InsaneScanner(ScannerBackend):
    """Linux/desktop scanner backend using pyinsane2."""

    def __init__(self):
        try:
            import pyinsane2

            self._pyinsane = pyinsane2
        except ImportError:
            raise RuntimeError("pyinsane2 is not available (Linux only)")

    def list_devices(self) -> list[dict]:
        """List available SANE scanner devices."""
        try:
            self._pyinsane.init()
            devices = self._pyinsane.get_devices()
            result = []
            for device in devices:
                result.append({
                    "id": device.name,
                    "name": str(device),
                    "backend": "sane",
                })
            self._pyinsane.exit()
            return result
        except Exception as e:
            logger.error("Failed to list SANE devices: %s", e)
            return []

    def scan(self, device_id: str, dpi: int = 300, color_mode: str = "color") -> Path:
        """Scan a document using a SANE device."""
        try:
            self._pyinsane.init()
            device = self._pyinsane.Scanner(name=device_id)
            device.options["resolution"].value = dpi
            mode_map = {
                "color": "Color",
                "grayscale": "Gray",
                "bw": "Lineart",
            }
            if "mode" in device.options:
                device.options["mode"].value = mode_map.get(color_mode, "Color")

            scan_session = device.scan(multiple=False)
            try:
                while True:
                    scan_session.scan.read()
            except EOFError:
                pass

            image = scan_session.images[-1]
            tmp_dir = Path(tempfile.mkdtemp())
            output_path = tmp_dir / "scan.png"
            image.save(str(output_path))
            self._pyinsane.exit()
            return output_path
        except Exception as e:
            logger.error("SANE scan failed: %s", e)
            raise RuntimeError(f"Scan failed: {e}") from e

    def get_device_capabilities(self, device_id: str) -> dict:
        """Get capabilities of a SANE device."""
        try:
            self._pyinsane.init()
            self._pyinsane.Scanner(name=device_id)
            capabilities = {
                "dpi_range": [100, 200, 300, 600],
                "color_modes": ["color", "grayscale", "bw"],
                "backend": "sane",
            }
            self._pyinsane.exit()
            return capabilities
        except Exception as e:
            logger.error("Failed to get SANE device capabilities: %s", e)
            return {}


class ScannerService:
    """Unified scanner service that auto-detects the appropriate backend."""

    _UNSET = object()

    def __init__(self, backend: ScannerBackend | None = _UNSET):
        if backend is self._UNSET:
            self._backend = self._auto_detect_backend()
        else:
            self._backend = backend
        self._temp_dirs: list[Path] = []

    @staticmethod
    def _auto_detect_backend() -> ScannerBackend | None:
        """Auto-detect the appropriate scanner backend for the current platform."""
        system = platform.system()
        if system == "Windows":
            try:
                return TwainScanner()
            except RuntimeError:
                pass
        else:  # Linux, Darwin
            try:
                return InsaneScanner()
            except RuntimeError:
                pass
        return None

    def list_devices(self) -> list[dict]:
        """List available scanner devices."""
        if self._backend is None:
            return []
        try:
            return self._backend.list_devices()
        except Exception as e:
            logger.error("Failed to list devices: %s", e)
            return []

    def scan(self, device_id: str, dpi: int = 300, color_mode: str = "color") -> Path:
        """Scan a document and return path to the scanned image.

        The caller is responsible for calling cleanup_scan() after the scanned
        file has been consumed to remove the temporary directory.
        """
        if self._backend is None:
            raise RuntimeError("No scanner backend available")
        result_path = self._backend.scan(device_id, dpi, color_mode)
        # Track the parent temp directory for cleanup
        self._temp_dirs.append(result_path.parent)
        return result_path

    def cleanup_scan(self, file_path: Path) -> None:
        """Remove the temporary directory associated with a scanned file."""
        import shutil

        scan_dir = file_path.parent
        try:
            if scan_dir.exists():
                shutil.rmtree(scan_dir)
            if scan_dir in self._temp_dirs:
                self._temp_dirs.remove(scan_dir)
        except OSError as e:
            logger.error("Failed to clean up scan directory %s: %s", scan_dir, e)

    def cleanup_all(self) -> None:
        """Remove all tracked temporary scan directories."""
        import shutil

        for scan_dir in list(self._temp_dirs):
            try:
                if scan_dir.exists():
                    shutil.rmtree(scan_dir)
            except OSError as e:
                logger.error("Failed to clean up scan directory %s: %s", scan_dir, e)
        self._temp_dirs.clear()

    def get_device_capabilities(self, device_id: str) -> dict:
        """Get capabilities of a specific device."""
        if self._backend is None:
            return {}
        try:
            return self._backend.get_device_capabilities(device_id)
        except Exception as e:
            logger.error("Failed to get device capabilities: %s", e)
            return {}
