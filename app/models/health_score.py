from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class HealthScoreRecord(Base):
    __tablename__ = "health_score_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    orphan_score: Mapped[float] = mapped_column(Float, nullable=False)
    lifecycle_score: Mapped[float] = mapped_column(Float, nullable=False)
    backup_score: Mapped[float] = mapped_column(Float, nullable=False)
    security_score: Mapped[float] = mapped_column(Float, nullable=False)
    storage_score: Mapped[float] = mapped_column(Float, nullable=False)
    sla_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
