"""Scheduled Reports API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.scheduled_report import ScheduledReport
from app.models.user import User
from app.schemas.scheduled_report import (
    ScheduledReportCreate,
    ScheduledReportResponse,
    ScheduledReportTriggerResponse,
    ScheduledReportUpdate,
)
from app.services.scheduled_reports import ScheduledReportService

router = APIRouter(tags=["scheduled-reports"])

report_service = ScheduledReportService()


@router.get("/api/reports", response_model=list[ScheduledReportResponse])
async def list_reports(
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """List all scheduled reports."""
    result = await db.execute(select(ScheduledReport))
    reports = result.scalars().all()
    return reports


@router.get("/api/reports/{report_id}", response_model=ScheduledReportResponse)
async def get_report(
    report_id: int,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific report by ID."""
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/api/reports", response_model=ScheduledReportResponse, status_code=201)
async def create_report(
    data: ScheduledReportCreate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new scheduled report."""
    report = ScheduledReport(
        name=data.name,
        schedule=data.schedule,
        report_type=data.report_type,
        recipients=data.recipients,
        filters=data.filters,
        is_active=data.is_active,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report


@router.put("/api/reports/{report_id}", response_model=ScheduledReportResponse)
async def update_report(
    report_id: int,
    data: ScheduledReportUpdate,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing scheduled report."""
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(report, key, value)

    await db.flush()
    await db.refresh(report)
    return report


@router.delete("/api/reports/{report_id}", status_code=204)
async def delete_report(
    report_id: int,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Delete a scheduled report."""
    result = await db.execute(
        select(ScheduledReport).where(ScheduledReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    await db.delete(report)
    await db.flush()


@router.post(
    "/api/reports/{report_id}/trigger",
    response_model=ScheduledReportTriggerResponse,
)
async def trigger_report(
    report_id: int,
    _user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a report generation and delivery."""
    result = await report_service.trigger_report(db, report_id)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])

    return ScheduledReportTriggerResponse(
        report_id=report_id,
        status=result["status"],
        message=result["message"],
    )
