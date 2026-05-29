from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class ScheduledReport(Base):
    __tablename__ = "scheduled_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    schedule: Mapped[str] = mapped_column(String(100), nullable=False)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recipients: Mapped[list] = mapped_column(JSON, nullable=False)
    filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )
