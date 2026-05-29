"""Ransomware detection service with behavioral monitoring."""

import collections
import math
import shutil
import threading
import time
from pathlib import Path

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

    class FileSystemEventHandler:  # type: ignore[no-redef]
        """Stub when watchdog is not installed."""

        pass

    class Observer:  # type: ignore[no-redef]
        """Stub when watchdog is not installed."""

        pass


class _EventHandler(FileSystemEventHandler):
    """Handles filesystem events and delegates to the detector."""

    def __init__(self, detector: "RansomwareDetector"):
        super().__init__()
        self._detector = detector

    def on_any_event(self, event):
        if not event.is_directory:
            self._detector._on_file_event(event)


class RansomwareDetector:
    """Monitors a directory for ransomware-like behavior patterns.

    Tracks filesystem operation rates and detects bulk encryption patterns
    by monitoring ops/sec in a sliding window.
    """

    def __init__(
        self,
        data_dir: str = "data",
        threshold_ops_per_sec: int = 50,
        window_seconds: int = 10,
        quarantine_dir: str = "quarantine",
    ):
        self.data_dir = Path(data_dir)
        self.threshold_ops_per_sec = threshold_ops_per_sec
        self.window_seconds = window_seconds
        self.quarantine_dir = Path(quarantine_dir)

        self._running = False
        self._observer = None
        self._start_time: float | None = None
        self._lock = threading.Lock()

        # Sliding window: deque of timestamps
        self._event_times: collections.deque = collections.deque()
        self._alerts: list[dict] = []
        self._files_monitored: int = 0
        self._alert_callback = None

    @property
    def is_running(self) -> bool:
        return self._running

    def set_alert_callback(self, callback):
        """Set a callback function to be called when an alert is created.

        The callback receives a dict with alert details.
        """
        self._alert_callback = callback

    def start(self) -> dict:
        """Start monitoring filesystem events."""
        if not WATCHDOG_AVAILABLE:
            return {
                "status": "error",
                "message": "watchdog not installed",
            }

        if self._running:
            return {"status": "already_running"}

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

        handler = _EventHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.data_dir), recursive=True)
        self._observer.start()
        self._running = True
        self._start_time = time.time()
        return {"status": "started"}

    def stop(self) -> dict:
        """Stop monitoring filesystem events."""
        if not self._running:
            return {"status": "not_running"}

        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        self._running = False
        self._start_time = None
        return {"status": "stopped"}

    def get_status(self) -> dict:
        """Return current monitoring status."""
        uptime = 0.0
        if self._running and self._start_time:
            uptime = time.time() - self._start_time

        return {
            "is_running": self._running,
            "watchdog_available": WATCHDOG_AVAILABLE,
            "uptime": round(uptime, 1),
            "ops_per_sec": self._current_ops_per_sec(),
            "files_monitored": self._files_monitored,
            "alerts_count": len(self._alerts),
            "threshold_ops_per_sec": self.threshold_ops_per_sec,
            "window_seconds": self.window_seconds,
            "data_dir": str(self.data_dir),
            "quarantine_dir": str(self.quarantine_dir),
        }

    def get_metrics(self) -> dict:
        """Return current metrics including ops/sec and sliding window data."""
        return {
            "ops_per_sec": self._current_ops_per_sec(),
            "window_seconds": self.window_seconds,
            "events_in_window": len(self._event_times),
            "threshold_ops_per_sec": self.threshold_ops_per_sec,
        }

    def _on_file_event(self, event) -> None:
        """Handle a filesystem event."""
        now = time.time()
        with self._lock:
            self._event_times.append(now)
            self._files_monitored += 1
            self._prune_window(now)
            self._check_threshold()

    def _prune_window(self, now: float) -> None:
        """Remove events outside the sliding window."""
        cutoff = now - self.window_seconds
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()

    def _current_ops_per_sec(self) -> float:
        """Calculate current ops per second in the sliding window."""
        now = time.time()
        with self._lock:
            self._prune_window(now)
            count = len(self._event_times)
        if self.window_seconds == 0:
            return 0.0
        return round(count / self.window_seconds, 2)

    def _check_threshold(self) -> None:
        """Check if ops/sec exceeds the threshold and create an alert if so."""
        count = len(self._event_times)
        ops_per_sec = count / self.window_seconds if self.window_seconds > 0 else 0

        if ops_per_sec >= self.threshold_ops_per_sec:
            alert = {
                "alert_type": "high_ops_rate",
                "severity": "high",
                "message": (
                    f"High file operation rate detected: "
                    f"{ops_per_sec:.1f} ops/sec exceeds threshold "
                    f"of {self.threshold_ops_per_sec} ops/sec"
                ),
                "details": {
                    "ops_per_sec": round(ops_per_sec, 2),
                    "threshold": self.threshold_ops_per_sec,
                    "events_in_window": count,
                    "window_seconds": self.window_seconds,
                },
                "detected_at": time.time(),
            }
            self._alerts.append(alert)

            if self._alert_callback:
                self._alert_callback(alert)

    @staticmethod
    def _calculate_entropy(data: bytes) -> float:
        """Calculate Shannon entropy of binary data.

        Returns a value between 0 (uniform) and 8 (maximum entropy for bytes).
        High entropy (>7.5) may indicate encrypted/compressed content.
        """
        if not data:
            return 0.0

        length = len(data)
        freq = collections.Counter(data)
        entropy = 0.0
        for count in freq.values():
            p = count / length
            if p > 0:
                entropy -= p * math.log2(p)
        return round(entropy, 4)

    def _quarantine_file(self, path: str) -> dict:
        """Move a suspicious file to the quarantine directory.

        Returns a dict describing the result.
        """
        src = Path(path)
        if not src.exists():
            return {"status": "error", "message": "File not found"}

        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        dest = self.quarantine_dir / src.name
        # Avoid overwriting existing quarantined files
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            counter = 1
            while dest.exists():
                dest = self.quarantine_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.move(str(src), str(dest))
        return {
            "status": "quarantined",
            "source": str(src),
            "destination": str(dest),
        }


# Module-level singleton instance
_detector_instance: RansomwareDetector | None = None
_detector_lock = threading.Lock()


def get_detector() -> RansomwareDetector:
    """Get or create the singleton RansomwareDetector instance."""
    global _detector_instance
    if _detector_instance is None:
        with _detector_lock:
            if _detector_instance is None:
                _detector_instance = RansomwareDetector()
    return _detector_instance


def reset_detector() -> None:
    """Reset the singleton detector (for testing)."""
    global _detector_instance
    with _detector_lock:
        if _detector_instance is not None:
            if _detector_instance.is_running:
                _detector_instance.stop()
        _detector_instance = None
