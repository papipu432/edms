import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class EncryptionKey(Base):
    __tablename__ = "encryption_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    key_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # "kek" or "dek"
    key_id_hex: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class KeyShare(Base):
    __tablename__ = "key_shares"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_generate_uuid
    )
    key_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("encryption_keys.id"), nullable=False
    )
    share_index: Mapped[int] = mapped_column(Integer, nullable=False)
    share_holder: Mapped[str] = mapped_column(String(255), nullable=False)
    is_distributed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
