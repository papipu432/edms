from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class DocumentSignature(Base):
    __tablename__ = "document_signatures"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    signer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    signature_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    qr_code_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    signed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    certificate_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
