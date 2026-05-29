import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.group import Base


class WorkflowStatus(str, enum.Enum):
    """Document workflow status states for Kanban board."""
    draft = "draft"
    pending_review = "pending_review"
    in_review = "in_review"
    changes_requested = "changes_requested"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


class WorkflowAction(str, enum.Enum):
    submit_review = "submit_review"
    approve = "approve"
    reject = "reject"
    request_changes = "request_changes"
    sign_off = "sign_off"
    move_stage = "move_stage"  # For Kanban drag-drop moves
    add_note = "add_note"      # For flow notes


class WorkflowStage(Base):
    """Workflow stages for Kanban-style document flow."""
    __tablename__ = "workflow_stages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[str | None] = mapped_column(String(16))  # For UI display
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    documents: Mapped[list["DocumentWorkflow"]] = relationship(
        back_populates="stage", lazy="selectin"
    )


class DocumentWorkflow(Base):
    """Current workflow state of a document (Kanban card)."""
    __tablename__ = "document_workflows"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    stage_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_stages.id"), nullable=False
    )
    assigned_to_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )
    assigned_to_position_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("org_positions.id")
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime)
    priority: Mapped[str] = mapped_column(String(16), default="normal")  # low, normal, high, urgent
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus), default=WorkflowStatus.draft
    )
    moved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    moved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id")
    )

    stage: Mapped["WorkflowStage"] = relationship(back_populates="documents")
    assigned_user: Mapped["User"] = relationship(foreign_keys=[assigned_to_user_id])
    moved_by: Mapped["User"] = relationship(foreign_keys=[moved_by_user_id])


class WorkflowNote(Base):
    """Flow notes attached to workflow moves (Kanban card annotations)."""
    __tablename__ = "workflow_notes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workflow_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_workflows.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    note_type: Mapped[str] = mapped_column(String(32), default="comment")  # comment, decision, annotation
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship()


class WorkflowEntry(Base):
    __tablename__ = "workflow_entries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[WorkflowAction] = mapped_column(Enum(WorkflowAction), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_stage_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("workflow_stages.id")
    )
    to_stage_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("workflow_stages.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship()
    from_stage: Mapped["WorkflowStage"] = relationship(foreign_keys=[from_stage_id])
    to_stage: Mapped["WorkflowStage"] = relationship(foreign_keys=[to_stage_id])
