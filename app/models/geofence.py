import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.group import Base


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class GeoFenceRule(Base):
    __tablename__ = "geofence_rules"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="global")
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_ip_ranges: Mapped[list | None] = mapped_column(JSON, nullable=True)
    denied_ip_ranges: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_countries: Mapped[list | None] = mapped_column(JSON, nullable=True)
    denied_countries: Mapped[list | None] = mapped_column(JSON, nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False, default="allow")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
