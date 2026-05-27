import asyncio
import shutil
from datetime import datetime, timezone

import httpx

from app.core.config import settings


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
        """Build environment variables for restic commands."""
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
                return {"status": "ok", "output": stdout.decode()}
            return {"status": "error", "detail": stderr.decode()}
        except Exception as e:
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
                return {
                    "status": "completed",
                    "output": stdout.decode(),
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "target": target,
                }
            return {
                "status": "failed",
                "detail": stderr.decode(),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "target": target,
            }
        except Exception as e:
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
