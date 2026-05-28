import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class SLAStatus(str, enum.Enum):
    on_time = "on_time"
    at_risk = "at_risk"
    breached = "breached"
    completed = "completed"


class SLAPolicy(Base):
    __tablename__ = "sla_policies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_templates.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), default="approval", nullable=False)
    max_duration_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    escalation_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DocumentSLA(Base):
    __tablename__ = "document_slas"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    policy_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sla_policies.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deadline_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[SLAStatus] = mapped_column(
        Enum(SLAStatus), default=SLAStatus.on_time, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
