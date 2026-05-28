"""Canvas/Whiteboard models for collaborative document arrangement."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.group import Base


class Canvas(Base):
    __tablename__ = "canvases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    items: Mapped[list["CanvasItem"]] = relationship(
        back_populates="canvas", cascade="all, delete-orphan"
    )
    connections: Mapped[list["CanvasConnection"]] = relationship(
        back_populates="canvas", cascade="all, delete-orphan"
    )


class CanvasItem(Base):
    __tablename__ = "canvas_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    canvas_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("canvases.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id"), nullable=True
    )
    note_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    y_position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    width: Mapped[float] = mapped_column(Float, nullable=False, default=200.0)
    height: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)

    canvas: Mapped["Canvas"] = relationship(back_populates="items")


class CanvasConnection(Base):
    __tablename__ = "canvas_connections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    canvas_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("canvases.id", ondelete="CASCADE"), nullable=False
    )
    from_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("canvas_items.id", ondelete="CASCADE"), nullable=False
    )
    to_item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("canvas_items.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    canvas: Mapped["Canvas"] = relationship(back_populates="connections")
