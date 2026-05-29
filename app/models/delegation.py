import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class DelegationScopeType(str, enum.Enum):
    all = "all"
    folder = "folder"


class Delegation(Base):
    __tablename__ = "delegations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    delegator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    delegate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scope_type: Mapped[DelegationScopeType] = mapped_column(
        Enum(DelegationScopeType), default=DelegationScopeType.all, nullable=False
    )
    scope_folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
