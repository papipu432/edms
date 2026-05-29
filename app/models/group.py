from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("groups.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    tenant_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=True
    )

    parent: Mapped["Group | None"] = relationship(
        "Group", remote_side=[id], back_populates="children", foreign_keys=[parent_id]
    )
    children: Mapped[list["Group"]] = relationship(
        "Group", back_populates="parent", foreign_keys=[parent_id]
    )
    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        back_populates="group", cascade="all, delete-orphan"
    )
