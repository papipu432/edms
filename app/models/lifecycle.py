import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class DocumentLifecycleState(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"
    up_to_date = "up_to_date"
    needs_re_review = "needs_re_review"
    expired = "expired"


class LifecycleType(str, enum.Enum):
    permanent = "permanent"
    expiring = "expiring"
    recurring = "recurring"


class DocumentLifecycle(Base):
    __tablename__ = "document_lifecycles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    lifecycle_type: Mapped[LifecycleType] = mapped_column(
        Enum(LifecycleType), nullable=False
    )
    state: Mapped[DocumentLifecycleState] = mapped_column(
        Enum(DocumentLifecycleState), default=DocumentLifecycleState.draft, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_reviewer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LifecycleTransition(Base):
    __tablename__ = "lifecycle_transitions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    lifecycle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_lifecycles.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[DocumentLifecycleState] = mapped_column(
        Enum(DocumentLifecycleState), nullable=False
    )
    to_state: Mapped[DocumentLifecycleState] = mapped_column(
        Enum(DocumentLifecycleState), nullable=False
    )
    transitioned_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
