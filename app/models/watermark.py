from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class WatermarkConfig(Base):
    __tablename__ = "watermark_configs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("groups.id"), nullable=True
    )
    text_template: Mapped[str] = mapped_column(
        String(500),
        default="{user} - {timestamp} - {doc_id} - CONFIDENTIAL",
        nullable=False,
    )
    opacity: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    position: Mapped[str] = mapped_column(
        String(32), default="diagonal", nullable=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
