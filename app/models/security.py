import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class SecurityAlert(Base):
    __tablename__ = "security_alerts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MonitoringConfig(Base):
    __tablename__ = "monitoring_config"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    config_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    config_value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
