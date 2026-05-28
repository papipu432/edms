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
from app.models.delegation import Delegation
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


async def _check_active_delegation(
    db: AsyncSession, delegator_id: str, delegate_id: str
) -> bool:
    """Check if delegate_id has an active delegation from delegator_id."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Delegation).where(
            Delegation.delegator_id == delegator_id,
            Delegation.delegate_id == delegate_id,
            Delegation.is_active == True,  # noqa: E712
            Delegation.start_date <= now,
            Delegation.end_date >= now,
        )
    )
    return result.scalar_one_or_none() is not None


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

    # Authorization check: admin bypasses, otherwise user must match step
    # criteria or hold an active delegation from the assigned user.
    is_admin = "admin" in current_user.role_codes
    via_delegation = False

    if not is_admin:
        authorized = False

        # Check if user matches the step's assigned user_id
        if current_step.user_id and current_step.user_id == current_user.id:
            authorized = True

        # Check if user has the required role_code
        if not authorized and current_step.role_code:
            if current_step.role_code in current_user.role_codes:
                authorized = True

        # Check if user holds an active delegation from the assigned user
        if not authorized and current_step.user_id:
            if await _check_active_delegation(
                db, current_step.user_id, current_user.id
            ):
                authorized = True
                via_delegation = True

        if not authorized:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to decide this approval step",
            )

    decision_value = ApprovalDecisionValue(data.decision)

    # Note delegation in comment if applicable
    comment = data.comment or ""
    if via_delegation:
        delegation_note = f"[Decided via delegation from user {current_step.user_id}]"
        comment = f"{delegation_note} {comment}".strip() if comment else delegation_note

    decision = ApprovalDecision(
        request_id=request_id,
        step_id=current_step.id,
        user_id=current_user.id,
        decision=decision_value,
        comment=comment if comment else data.comment,
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
        # For parallel approval type, a single approval at this step is
        # sufficient to advance ("any-of" semantics). Sequential type requires
        # steps to be completed in order ("all in order"). Both advance on a
        # single approval decision at the current step_order.
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
