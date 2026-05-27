import asyncio
import logging
import shutil
from datetime import datetime, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class BackupService:
    """Service for managing Restic backups with MinIO storage."""

    def __init__(self) -> None:
        self._restic_available: bool | None = None

    @property
    def restic_installed(self) -> bool:
        """Check if the restic binary is available on the system."""
        if self._restic_available is None:
            self._restic_available = shutil.which("restic") is not None
        return self._restic_available

    def _get_env(self, target: str = "primary") -> dict[str, str]:
        """Build environment variables for restic commands.

        Note: Credential values are passed via environment variables only,
        never logged or written to disk.
        """
        env: dict[str, str] = {}
        if settings.RESTIC_REPOSITORY:
            env["RESTIC_REPOSITORY"] = settings.RESTIC_REPOSITORY
        if settings.RESTIC_PASSWORD:
            env["RESTIC_PASSWORD"] = settings.RESTIC_PASSWORD
        if target == "primary":
            if settings.MINIO_PRIMARY_ENDPOINT:
                env["AWS_ACCESS_KEY_ID"] = settings.MINIO_PRIMARY_ACCESS_KEY
                env["AWS_SECRET_ACCESS_KEY"] = settings.MINIO_PRIMARY_SECRET_KEY
        else:
            if settings.MINIO_DR_ENDPOINT:
                env["AWS_ACCESS_KEY_ID"] = settings.MINIO_DR_ACCESS_KEY
                env["AWS_SECRET_ACCESS_KEY"] = settings.MINIO_DR_SECRET_KEY
        return env

    def pre_encrypt_backup_data(
        self, data: bytes, backup_kek: bytes
    ) -> bytes:
        """Pre-encrypt backup data with backup-specific KEK before sending to restic.

        This adds an additional encryption layer on top of restic's own encryption,
        ensuring data is protected even if restic credentials are compromised.
        """
        from app.services.backup_kek_manager import BackupKEKManager

        manager = BackupKEKManager()
        return manager.encrypt_for_backup(data, backup_kek)

    def decrypt_backup_data(
        self, encrypted_data: bytes, backup_kek: bytes
    ) -> bytes:
        """Decrypt backup data that was pre-encrypted with backup KEK."""
        from app.services.backup_kek_manager import BackupKEKManager

        manager = BackupKEKManager()
        return manager.decrypt_from_backup(encrypted_data, backup_kek)

    async def init_repository(self) -> dict:
        """Initialize a Restic repository."""
        if not self.restic_installed:
            return {"status": "error", "detail": "restic binary not found"}

        try:
            env = self._get_env()
            proc = await asyncio.create_subprocess_exec(
                "restic", "init",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info("Restic repository initialized successfully")
                return {"status": "ok", "output": stdout.decode()}
            logger.warning("Restic init failed with return code %d", proc.returncode)
            return {"status": "error", "detail": stderr.decode()}
        except Exception as e:
            logger.error("Failed to initialize restic repository: %s", type(e).__name__)
            return {"status": "error", "detail": str(e)}

    async def run_backup(self, target: str = "primary") -> dict:
        """Execute a backup using restic."""
        if not self.restic_installed:
            return {
                "status": "error",
                "detail": "restic binary not found",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

        started_at = datetime.now(timezone.utc)
        try:
            env = self._get_env(target)
            backup_path = settings.STORAGE_PATH
            proc = await asyncio.create_subprocess_exec(
                "restic", "backup", backup_path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            finished_at = datetime.now(timezone.utc)
            if proc.returncode == 0:
                logger.info("Backup completed successfully to target=%s", target)
                return {
                    "status": "completed",
                    "output": stdout.decode(),
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "target": target,
                }
            logger.warning("Backup failed for target=%s", target)
            return {
                "status": "failed",
                "detail": stderr.decode(),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "target": target,
            }
        except Exception as e:
            logger.error("Backup exception for target=%s: %s", target, type(e).__name__)
            return {
                "status": "failed",
                "detail": str(e),
                "started_at": started_at.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "target": target,
            }

    async def list_snapshots(self) -> dict:
        """List Restic snapshots."""
        if not self.restic_installed:
            return {"status": "error", "detail": "restic binary not found", "snapshots": []}

        try:
            env = self._get_env()
            proc = await asyncio.create_subprocess_exec(
                "restic", "snapshots", "--json",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return {"status": "ok", "snapshots_raw": stdout.decode()}
            return {"status": "error", "detail": stderr.decode(), "snapshots": []}
        except Exception as e:
            return {"status": "error", "detail": str(e), "snapshots": []}

    async def get_status(self) -> dict:
        """Check backup system status."""
        return {
            "restic_installed": self.restic_installed,
            "repository_configured": bool(settings.RESTIC_REPOSITORY),
            "primary_endpoint_configured": bool(settings.MINIO_PRIMARY_ENDPOINT),
            "dr_endpoint_configured": bool(settings.MINIO_DR_ENDPOINT),
            "schedule": settings.BACKUP_SCHEDULE,
            "retention_days": settings.BACKUP_RETENTION_DAYS,
        }

    async def check_minio_connection(
        self, endpoint: str, access_key: str, secret_key: str
    ) -> dict:
        """Verify MinIO connectivity via health endpoint."""
        if not endpoint:
            return {"connected": False, "error": "No endpoint configured"}

        url = endpoint.rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/minio/health/live")
                if resp.status_code == 200:
                    return {"connected": True, "endpoint": endpoint}
                return {
                    "connected": False,
                    "endpoint": endpoint,
                    "error": f"HTTP {resp.status_code}",
                }
        except Exception as e:
            return {"connected": False, "endpoint": endpoint, "error": str(e)}
