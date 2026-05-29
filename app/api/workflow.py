from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.user import User
from app.models.workflow import (
    WorkflowAction, 
    WorkflowEntry, 
    WorkflowStage, 
    DocumentWorkflow, 
    WorkflowNote,
    WorkflowStatus
)
from app.schemas.workflow import (
    WorkflowActionRequest, 
    WorkflowEntryResponse,
    WorkflowStageCreate,
    WorkflowStageUpdate,
    DocumentWorkflowMoveRequest,
    WorkflowNoteCreate,
    KanbanBoardResponse
)

router = APIRouter(tags=["workflow"])

# Mapping of workflow actions to the roles permitted to perform them
_ACTION_ALLOWED_ROLES: dict[WorkflowAction, list[str]] = {
    WorkflowAction.submit_review: ["editor", "admin", "annotator"],
    WorkflowAction.approve: ["approver", "admin"],
    WorkflowAction.reject: ["reviewer", "admin"],
    WorkflowAction.request_changes: ["reviewer", "admin"],
    WorkflowAction.sign_off: ["approver", "admin"],
    WorkflowAction.move_stage: ["editor", "reviewer", "approver", "admin"],
    WorkflowAction.add_note: ["editor", "reviewer", "approver", "admin", "annotator"],
}


@router.get("/api/workflow/stages", response_model=list[dict])
async def list_workflow_stages(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all workflow stages for Kanban board."""
    result = await db.execute(
        select(WorkflowStage)
        .where(WorkflowStage.is_active == True)
        .order_by(WorkflowStage.order_index)
    )
    stages = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "code": s.code,
            "description": s.description,
            "order_index": s.order_index,
            "color": s.color,
        }
        for s in stages
    ]


@router.post("/api/workflow/stages", status_code=201, response_model=dict)
async def create_workflow_stage(
    data: WorkflowStageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new workflow stage."""
    # Check admin permission
    if "admin" not in current_user.role_codes:
        raise HTTPException(status_code=403, detail="Admin role required")
    
    stage = WorkflowStage(
        name=data.name,
        code=data.code,
        description=data.description,
        order_index=data.order_index,
        color=data.color,
    )
    db.add(stage)
    await db.flush()
    await db.refresh(stage)
    return {"id": stage.id, "code": stage.code, "name": stage.name}


@router.put("/api/workflow/stages/{stage_id}", response_model=dict)
async def update_workflow_stage(
    stage_id: int,
    data: WorkflowStageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update workflow stage (including reordering)."""
    if "admin" not in current_user.role_codes:
        raise HTTPException(status_code=403, detail="Admin role required")
    
    stage = await db.get(WorkflowStage, stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    
    if data.name is not None:
        stage.name = data.name
    if data.description is not None:
        stage.description = data.description
    if data.color is not None:
        stage.color = data.color
    if data.order_index is not None:
        stage.order_index = data.order_index
    
    await db.flush()
    return {"id": stage.id, "name": stage.name}


@router.get("/api/workflow/kanban", response_model=KanbanBoardResponse)
async def get_kanban_board(
    group_id: int | None = Query(None, description="Filter by document group"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full Kanban board with documents organized by stage."""
    # Get all stages
    stages_result = await db.execute(
        select(WorkflowStage)
        .where(WorkflowStage.is_active == True)
        .order_by(WorkflowStage.order_index)
    )
    stages = stages_result.scalars().all()
    
    # Get all document workflows
    query = select(DocumentWorkflow).join(Document)
    if group_id:
        query = query.where(Document.group_id == group_id)
    
    workflows_result = await db.execute(query)
    workflows = workflows_result.scalars().all()
    
    # Build board response
    columns = []
    for stage in stages:
        stage_workflows = [wf for wf in workflows if wf.stage_id == stage.id]
        cards = []
        for wf in stage_workflows:
            doc = await db.get(Document, wf.document_id)
            if doc:
                cards.append({
                    "id": wf.id,
                    "document_id": wf.document_id,
                    "title": doc.title,
                    "status": wf.status.value,
                    "priority": wf.priority,
                    "assigned_to_user_id": wf.assigned_to_user_id,
                    "assigned_to_position_id": wf.assigned_to_position_id,
                    "due_date": wf.due_date.isoformat() if wf.due_date else None,
                    "moved_at": wf.moved_at.isoformat() if wf.moved_at else None,
                })
        
        columns.append({
            "stage_id": stage.id,
            "stage_name": stage.name,
            "stage_code": stage.code,
            "stage_color": stage.color,
            "cards": cards,
        })
    
    return {"columns": columns, "total_documents": len(workflows)}


@router.post("/api/workflow/documents/{document_id}/move", response_model=dict)
async def move_document_stage(
    document_id: int,
    data: DocumentWorkflowMoveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move document to different stage (Kanban drag-drop)."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get or create workflow entry for this document
    workflow = await db.get(DocumentWorkflow, document_id)  # Using document_id as PK reference
    
    if not workflow:
        # Create new workflow entry
        workflow = DocumentWorkflow(
            document_id=document_id,
            stage_id=data.to_stage_id,
            assigned_to_user_id=data.assign_to_user_id,
            assigned_to_position_id=data.assign_to_position_id,
            status=WorkflowStatus.pending_review if data.to_stage_id else WorkflowStatus.draft,
            moved_by_user_id=current_user.id,
        )
        db.add(workflow)
    else:
        from_stage_id = workflow.stage_id
        workflow.stage_id = data.to_stage_id
        workflow.moved_by_user_id = current_user.id
        
        # Create workflow entry for audit
        entry = WorkflowEntry(
            document_id=document_id,
            user_id=current_user.id,
            action=WorkflowAction.move_stage,
            comment=data.comment,
            from_stage_id=from_stage_id,
            to_stage_id=data.to_stage_id,
        )
        db.add(entry)
    
    # Add note if provided
    if data.note:
        note = WorkflowNote(
            workflow_id=workflow.id,
            user_id=current_user.id,
            note_type="comment",
            content=data.note,
        )
        db.add(note)
    
    await db.flush()
    await db.refresh(workflow)
    
    return {
        "success": True,
        "document_id": document_id,
        "new_stage_id": workflow.stage_id,
        "moved_at": workflow.moved_at.isoformat() if workflow.moved_at else None,
    }


@router.post("/api/workflow/documents/{document_id}/notes", status_code=201)
async def add_workflow_note(
    document_id: int,
    data: WorkflowNoteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a flow note to a workflow (Kanban card annotation)."""
    workflow = await db.get(DocumentWorkflow, document_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    note = WorkflowNote(
        workflow_id=workflow.id,
        user_id=current_user.id,
        note_type=data.note_type,
        content=data.content,
    )
    db.add(note)
    await db.flush()
    await db.refresh(note)
    
    # Also create workflow entry
    entry = WorkflowEntry(
        document_id=document_id,
        user_id=current_user.id,
        action=WorkflowAction.add_note,
        comment=data.content,
    )
    db.add(entry)
    await db.flush()
    
    return {"id": note.id, "created_at": note.created_at.isoformat()}


@router.get("/api/workflow/documents/{document_id}/notes", response_model=list[dict])
async def get_workflow_notes(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all notes for a workflow."""
    workflow = await db.get(DocumentWorkflow, document_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    result = await db.execute(
        select(WorkflowNote)
        .where(WorkflowNote.workflow_id == workflow.id)
        .order_by(WorkflowNote.created_at)
    )
    notes = result.scalars().all()
    
    return [
        {
            "id": n.id,
            "user_id": n.user_id,
            "note_type": n.note_type,
            "content": n.content,
            "created_at": n.created_at.isoformat(),
        }
        for n in notes
    ]


@router.post(
    "/api/documents/{document_id}/workflow/{action}",
    response_model=WorkflowEntryResponse,
    status_code=201,
)
async def create_workflow_action(
    document_id: int,
    action: WorkflowAction,
    data: WorkflowActionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check role permissions for the requested action
    allowed_roles = _ACTION_ALLOWED_ROLES.get(action, [])
    user_roles = current_user.role_codes
    if not any(role in user_roles for role in allowed_roles):
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions for action '{action.value}'",
        )

    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    entry = WorkflowEntry(
        document_id=document_id,
        user_id=current_user.id,
        action=action,
        comment=data.comment,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.get(
    "/api/documents/{document_id}/workflow",
    response_model=list[WorkflowEntryResponse],
)
async def get_workflow_history(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    result = await db.execute(
        select(WorkflowEntry)
        .where(WorkflowEntry.document_id == document_id)
        .order_by(WorkflowEntry.created_at)
    )
    return list(result.scalars().all())

