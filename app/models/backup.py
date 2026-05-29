import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


def _gen_uuid() -> str:
    return str(uuid.uuid4())


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_gen_uuid
    )
    job_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="full"
    )  # full / incremental
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending / running / completed / failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    files_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target: Mapped[str] = mapped_column(
        String(50), nullable=False, default="primary"
    )  # primary / dr
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class BackupSchedule(Base):
    __tablename__ = "backup_schedules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_gen_uuid
    )
    cron_expression: Mapped[str] = mapped_column(
        String(100), nullable=False, default="0 2 * * *"
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class BackupConfig(Base):
    __tablename__ = "backup_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_gen_uuid
    )
    config_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    config_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class BackupEncryptionKey(Base):
    """Stores the KMS-wrapped backup KEK, separate from production KEK."""

    __tablename__ = "backup_encryption_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_gen_uuid
    )
    key_id_hex: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    wrapped_key_blob: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    purpose: Mapped[str] = mapped_column(
        String(50), nullable=False, default="backup"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
