from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class SearchHistory(Base):
    __tablename__ = "search_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    query_text: Mapped[str] = mapped_column(String(1000), nullable=False)
    filters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
