from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.document import Document
from app.models.sla import DocumentSLA, SLAPolicy, SLAStatus
from app.models.user import User
from app.schemas.sla import (
    DocumentSLAResponse,
    SLADashboardResponse,
    SLAPolicyCreate,
    SLAPolicyResponse,
)
from app.services.notifications import get_notification_manager

router = APIRouter(tags=["sla"])


@router.post(
    "/api/sla-policies",
    response_model=SLAPolicyResponse,
    status_code=201,
)
async def create_sla_policy(
    data: SLAPolicyCreate,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create an SLA policy (admin only)."""
    policy = SLAPolicy(
        folder_id=data.folder_id,
        template_id=data.template_id,
        action=data.action,
        max_duration_hours=data.max_duration_hours,
        escalation_role=data.escalation_role,
        is_active=True,
    )
    db.add(policy)
    await db.flush()
    await db.refresh(policy)
    return policy


@router.get(
    "/api/sla-policies",
    response_model=list[SLAPolicyResponse],
)
async def list_sla_policies(
    db: AsyncSession = Depends(get_db),
):
    """List all SLA policies."""
    result = await db.execute(
        select(SLAPolicy).order_by(SLAPolicy.created_at)
    )
    return list(result.scalars().all())


@router.delete(
    "/api/sla-policies/{policy_id}",
    status_code=204,
)
async def delete_sla_policy(
    policy_id: int,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Delete an SLA policy (admin only)."""
    policy = await db.get(SLAPolicy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="SLA policy not found")
    await db.delete(policy)
    await db.flush()


@router.post(
    "/api/documents/{document_id}/sla/start",
    response_model=DocumentSLAResponse,
    status_code=201,
)
async def start_sla(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start SLA tracking for a document - finds matching policy and creates DocumentSLA."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Find matching policy by template_id or folder_id
    policy = None
    if document.template_id:
        result = await db.execute(
            select(SLAPolicy).where(
                SLAPolicy.template_id == document.template_id,
                SLAPolicy.is_active == True,  # noqa: E712
            )
        )
        policy = result.scalar_one_or_none()

    if not policy:
        result = await db.execute(
            select(SLAPolicy).where(
                SLAPolicy.folder_id == document.group_id,
                SLAPolicy.is_active == True,  # noqa: E712
            )
        )
        policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=404,
            detail="No SLA policy found for this document",
        )

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=policy.max_duration_hours)

    doc_sla = DocumentSLA(
        document_id=document_id,
        policy_id=policy.id,
        started_at=now,
        deadline_at=deadline,
        status=SLAStatus.on_time,
    )
    db.add(doc_sla)
    await db.flush()
    await db.refresh(doc_sla)

    percent_elapsed = _compute_percent_elapsed(doc_sla.started_at, doc_sla.deadline_at)
    return DocumentSLAResponse(
        id=doc_sla.id,
        document_id=doc_sla.document_id,
        policy_id=doc_sla.policy_id,
        started_at=doc_sla.started_at,
        deadline_at=doc_sla.deadline_at,
        status=doc_sla.status.value,
        completed_at=doc_sla.completed_at,
        escalated=doc_sla.escalated,
        percent_elapsed=percent_elapsed,
    )


@router.get(
    "/api/documents/{document_id}/sla",
    response_model=DocumentSLAResponse | None,
)
async def get_document_sla(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the SLA status for a document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(DocumentSLA)
        .where(DocumentSLA.document_id == document_id)
        .order_by(DocumentSLA.started_at.desc())
    )
    doc_sla = result.scalars().first()
    if not doc_sla:
        return None

    percent_elapsed = _compute_percent_elapsed(doc_sla.started_at, doc_sla.deadline_at)
    return DocumentSLAResponse(
        id=doc_sla.id,
        document_id=doc_sla.document_id,
        policy_id=doc_sla.policy_id,
        started_at=doc_sla.started_at,
        deadline_at=doc_sla.deadline_at,
        status=doc_sla.status.value,
        completed_at=doc_sla.completed_at,
        escalated=doc_sla.escalated,
        percent_elapsed=percent_elapsed,
    )


@router.get(
    "/api/sla/dashboard",
    response_model=SLADashboardResponse,
)
async def sla_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get SLA compliance dashboard metrics."""
    result = await db.execute(select(DocumentSLA))
    all_slas = list(result.scalars().all())

    total = len(all_slas)
    on_time = 0
    at_risk = 0
    breached = 0
    completed = 0

    for sla in all_slas:
        if sla.status == SLAStatus.completed:
            completed += 1
        elif sla.status == SLAStatus.breached:
            breached += 1
        elif sla.status == SLAStatus.at_risk:
            at_risk += 1
        else:
            on_time += 1

    compliance_rate = 0.0
    if total > 0:
        compliance_rate = ((on_time + completed) / total) * 100

    return SLADashboardResponse(
        total=total,
        on_time=on_time,
        at_risk=at_risk,
        breached=breached,
        completed=completed,
        compliance_rate=round(compliance_rate, 2),
    )


@router.put(
    "/api/sla/check-breaches",
    status_code=200,
)
async def check_breaches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check all active SLAs and update statuses. Notify escalation_role on breach."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(DocumentSLA).where(
            DocumentSLA.status.in_([SLAStatus.on_time, SLAStatus.at_risk])
        )
    )
    active_slas = list(result.scalars().all())

    updated_count = 0
    breached_count = 0
    notification_manager = get_notification_manager()

    for sla in active_slas:
        percent = _compute_percent_elapsed(sla.started_at, sla.deadline_at, now)
        old_status = sla.status

        if percent > 100:
            sla.status = SLAStatus.breached
        elif percent > 80:
            sla.status = SLAStatus.at_risk

        if sla.status != old_status:
            updated_count += 1

            if sla.status == SLAStatus.breached and not sla.escalated:
                breached_count += 1
                sla.escalated = True
                # Create notification for breach
                await notification_manager.create_notification(
                    db,
                    None,
                    "sla_breach",
                    "SLA Breached",
                    f"Document SLA #{sla.id} has breached its deadline.",
                    {"sla_id": sla.id, "document_id": sla.document_id},
                )

    await db.flush()

    return {
        "checked": len(active_slas),
        "updated": updated_count,
        "breached": breached_count,
    }


def _compute_percent_elapsed(
    started_at: datetime,
    deadline_at: datetime,
    now: datetime | None = None,
) -> float:
    """Compute percent elapsed between started_at and deadline_at."""
    if now is None:
        now = datetime.now(timezone.utc)
    # Ensure timezone awareness
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if deadline_at.tzinfo is None:
        deadline_at = deadline_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    total_duration = (deadline_at - started_at).total_seconds()
    if total_duration <= 0:
        return 100.0
    elapsed = (now - started_at).total_seconds()
    return round((elapsed / total_duration) * 100, 2)
