import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.group import Base


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class ComplianceReport(Base):
    __tablename__ = "compliance_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    report_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    format: Mapped[str] = mapped_column(String(16), default="json", nullable=False)
