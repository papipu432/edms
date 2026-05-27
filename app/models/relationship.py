import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.group import Base


class RelationshipType(str, enum.Enum):
    parent = "parent"
    child = "child"
    related = "related"
    supersedes = "supersedes"
    references = "references"


class DocumentRelationship(Base):
    __tablename__ = "document_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relationship_type",
            name="uq_source_target_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    target_document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
