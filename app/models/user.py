import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.group import Base


class RoleName(str, enum.Enum):
    admin = "admin"
    reviewer = "reviewer"
    editor = "editor"
    annotator = "annotator"
    approver = "approver"


# Association table for many-to-many User <-> Role
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE")),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary=user_roles, back_populates="users", lazy="selectin"
    )
    folder_assignments: Mapped[list["FolderAssignment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[RoleName] = mapped_column(Enum(RoleName), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    users: Mapped[list["User"]] = relationship(
        secondary=user_roles, back_populates="roles"
    )


class FolderAssignment(Base):
    __tablename__ = "folder_assignments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_path: Mapped[str] = mapped_column(String(500), nullable=False)
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roles.id"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="folder_assignments")
    role: Mapped["Role"] = relationship(lazy="selectin")
