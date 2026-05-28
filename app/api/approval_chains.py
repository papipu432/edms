from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.approval import (
    ApprovalChain,
    ApprovalDecision,
    ApprovalDecisionValue,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStep,
    ApprovalType,
)
from app.models.document import Document
from app.models.user import User
from app.schemas.approval import (
    ApprovalChainCreate,
    ApprovalChainListResponse,
    ApprovalChainResponse,
    ApprovalDecisionCreate,
    ApprovalDecisionResponse,
    ApprovalRequestResponse,
    ApprovalStepResponse,
)
from app.services.notifications import get_notification_manager

router = APIRouter(tags=["approval-chains"])


@router.post(
    "/api/approval-chains",
    response_model=ApprovalChainResponse,
    status_code=201,
)
async def create_approval_chain(
    data: ApprovalChainCreate,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    chain = ApprovalChain(
        name=data.name,
        folder_id=data.folder_id,
        template_id=data.template_id,
        is_active=True,
    )
    db.add(chain)
    await db.flush()
    await db.refresh(chain)

    steps = []
    for step_data in data.steps:
        step = ApprovalStep(
            chain_id=chain.id,
            step_order=step_data.step_order,
            approval_type=ApprovalType(step_data.approval_type),
            role_code=step_data.role_code,
            user_id=step_data.user_id,
            timeout_hours=step_data.timeout_hours,
        )
        db.add(step)
        steps.append(step)
    await db.flush()
    for step in steps:
        await db.refresh(step)

    return ApprovalChainResponse(
        id=chain.id,
        name=chain.name,
        folder_id=chain.folder_id,
        template_id=chain.template_id,
        is_active=chain.is_active,
        created_at=chain.created_at,
        steps=[ApprovalStepResponse.model_validate(s) for s in steps],
    )


@router.get(
    "/api/approval-chains",
    response_model=list[ApprovalChainListResponse],
)
async def list_approval_chains(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ApprovalChain).order_by(ApprovalChain.created_at)
    )
    return list(result.scalars().all())


@router.get(
    "/api/approval-chains/{chain_id}",
    response_model=ApprovalChainResponse,
)
async def get_approval_chain(
    chain_id: int,
    db: AsyncSession = Depends(get_db),
):
    chain = await db.get(ApprovalChain, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Approval chain not found")

    result = await db.execute(
        select(ApprovalStep)
        .where(ApprovalStep.chain_id == chain_id)
        .order_by(ApprovalStep.step_order)
    )
    steps = list(result.scalars().all())

    return ApprovalChainResponse(
        id=chain.id,
        name=chain.name,
        folder_id=chain.folder_id,
        template_id=chain.template_id,
        is_active=chain.is_active,
        created_at=chain.created_at,
        steps=[ApprovalStepResponse.model_validate(s) for s in steps],
    )


@router.delete(
    "/api/approval-chains/{chain_id}",
    status_code=204,
)
async def delete_approval_chain(
    chain_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    chain = await db.get(ApprovalChain, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Approval chain not found")
    await db.delete(chain)
    await db.flush()


@router.post(
    "/api/documents/{document_id}/approval-requests",
    response_model=ApprovalRequestResponse,
    status_code=201,
)
async def submit_for_approval(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Find matching chain by folder_id or template_id
    chain = None
    if document.template_id:
        result = await db.execute(
            select(ApprovalChain).where(
                ApprovalChain.template_id == document.template_id,
                ApprovalChain.is_active == True,  # noqa: E712
            )
        )
        chain = result.scalar_one_or_none()

    if not chain:
        result = await db.execute(
            select(ApprovalChain).where(
                ApprovalChain.folder_id == document.group_id,
                ApprovalChain.is_active == True,  # noqa: E712
            )
        )
        chain = result.scalar_one_or_none()

    if not chain:
        raise HTTPException(
            status_code=404,
            detail="No approval chain found for this document",
        )

    request = ApprovalRequest(
        document_id=document_id,
        chain_id=chain.id,
        status=ApprovalStatus.pending,
        current_step_order=1,
        submitted_by=current_user.id,
    )
    db.add(request)
    await db.flush()
    await db.refresh(request)
    return request


@router.post(
    "/api/approval-requests/{request_id}/decide",
    response_model=ApprovalDecisionResponse,
    status_code=201,
)
async def decide_approval(
    request_id: int,
    data: ApprovalDecisionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    approval_request = await db.get(ApprovalRequest, request_id)
    if not approval_request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval_request.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="Approval request is not pending")

    # Find the current step
    result = await db.execute(
        select(ApprovalStep).where(
            ApprovalStep.chain_id == approval_request.chain_id,
            ApprovalStep.step_order == approval_request.current_step_order,
        )
    )
    current_step = result.scalar_one_or_none()
    if not current_step:
        raise HTTPException(status_code=404, detail="Current approval step not found")

    decision_value = ApprovalDecisionValue(data.decision)

    decision = ApprovalDecision(
        request_id=request_id,
        step_id=current_step.id,
        user_id=current_user.id,
        decision=decision_value,
        comment=data.comment,
    )
    db.add(decision)
    await db.flush()
    await db.refresh(decision)

    notification_manager = get_notification_manager()

    if decision_value == ApprovalDecisionValue.rejected:
        approval_request.status = ApprovalStatus.rejected
        approval_request.completed_at = datetime.now(timezone.utc)
        await db.flush()

        # Notify submitter of rejection
        await notification_manager.create_notification(
            db,
            approval_request.submitted_by,
            "approval_rejected",
            "Approval Rejected",
            f"Your approval request was rejected at step {approval_request.current_step_order}.",
            {"request_id": request_id, "document_id": approval_request.document_id},
        )
    else:
        # Check if there is a next step
        result = await db.execute(
            select(ApprovalStep).where(
                ApprovalStep.chain_id == approval_request.chain_id,
                ApprovalStep.step_order > approval_request.current_step_order,
            ).order_by(ApprovalStep.step_order)
        )
        next_step = result.scalars().first()

        if next_step:
            approval_request.current_step_order = next_step.step_order
            await db.flush()
        else:
            # All steps approved
            approval_request.status = ApprovalStatus.approved
            approval_request.completed_at = datetime.now(timezone.utc)
            await db.flush()

            await notification_manager.create_notification(
                db,
                approval_request.submitted_by,
                "approval_approved",
                "Approval Completed",
                "Your approval request has been fully approved.",
                {"request_id": request_id, "document_id": approval_request.document_id},
            )

    return decision


@router.get(
    "/api/documents/{document_id}/approval-status",
    response_model=ApprovalRequestResponse | None,
)
async def get_approval_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.document_id == document_id)
        .order_by(ApprovalRequest.submitted_at.desc())
    )
    request = result.scalars().first()
    return request
