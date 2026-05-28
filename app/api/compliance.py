"""Compliance reporting API router."""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.compliance import ComplianceReport
from app.models.user import User
from app.schemas.compliance import (
    ComplianceReportListItem,
    ComplianceReportRequest,
    ComplianceReportResponse,
)
from app.services.compliance import ComplianceReportService

router = APIRouter(tags=["compliance"])

VALID_REPORT_TYPES = [
    "access_log",
    "encryption_status",
    "retention_compliance",
    "permission_audit",
]

compliance_service = ComplianceReportService()


async def _require_admin(user: User) -> None:
    """Check that the current user has admin role."""
    if "admin" not in user.role_codes:
        raise HTTPException(status_code=403, detail="Admin role required")


@router.post("/api/compliance/reports", response_model=ComplianceReportResponse)
async def generate_compliance_report(
    request: ComplianceReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a new compliance report (admin only)."""
    await _require_admin(current_user)

    if request.report_type not in VALID_REPORT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report_type. Must be one of: {VALID_REPORT_TYPES}",
        )

    # Parse dates
    start_date = None
    end_date = None
    if request.start_date:
        try:
            start_date = datetime.fromisoformat(request.start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if request.end_date:
        try:
            end_date = datetime.fromisoformat(request.end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    # Generate report data
    if request.report_type == "access_log":
        data = await compliance_service.generate_access_log_report(
            db, start_date, end_date
        )
    elif request.report_type == "encryption_status":
        data = await compliance_service.generate_encryption_status_report(db)
    elif request.report_type == "retention_compliance":
        data = await compliance_service.generate_retention_compliance_report(db)
    elif request.report_type == "permission_audit":
        data = await compliance_service.generate_permission_audit_report(db)
    else:
        raise HTTPException(status_code=400, detail="Unknown report type")

    # Save report
    report = ComplianceReport(
        report_type=request.report_type,
        generated_by=current_user.id,
        start_date=start_date,
        end_date=end_date,
        report_data=data,
        format=request.format,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)

    return ComplianceReportResponse(
        id=report.id,
        report_type=report.report_type,
        generated_at=report.generated_at,
        data=data,
        export_url=f"/api/compliance/reports/{report.id}/export?format=csv",
    )


@router.get("/api/compliance/reports", response_model=list[ComplianceReportListItem])
async def list_compliance_reports(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List generated compliance reports (admin only)."""
    await _require_admin(current_user)

    result = await db.execute(
        select(ComplianceReport).order_by(ComplianceReport.generated_at.desc())
    )
    reports = result.scalars().all()

    return [
        ComplianceReportListItem(
            id=r.id,
            report_type=r.report_type,
            generated_at=r.generated_at,
            format=r.format,
        )
        for r in reports
    ]


@router.get("/api/compliance/reports/{report_id}", response_model=ComplianceReportResponse)
async def get_compliance_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific compliance report."""
    await _require_admin(current_user)

    result = await db.execute(
        select(ComplianceReport).where(ComplianceReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return ComplianceReportResponse(
        id=report.id,
        report_type=report.report_type,
        generated_at=report.generated_at,
        data=report.report_data or {},
        export_url=f"/api/compliance/reports/{report.id}/export?format=csv",
    )


@router.get("/api/compliance/reports/{report_id}/export")
async def export_compliance_report(
    report_id: int,
    format: str = "csv",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a compliance report as CSV."""
    await _require_admin(current_user)

    result = await db.execute(
        select(ComplianceReport).where(ComplianceReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if format != "csv":
        raise HTTPException(status_code=400, detail="Only CSV export is supported")

    data = report.report_data or {}
    output = io.StringIO()
    writer = csv.writer(output)

    # Generate CSV based on report type
    entries = data.get("entries", [])
    if report.report_type == "access_log":
        writer.writerow(["actor_username", "document_id", "action", "count"])
        for entry in entries:
            writer.writerow([
                entry.get("actor_username", ""),
                entry.get("document_id", ""),
                entry.get("action", ""),
                entry.get("count", 0),
            ])
    elif report.report_type == "encryption_status":
        writer.writerow(["metric", "value"])
        writer.writerow(["total_documents", data.get("total_documents", 0)])
        writer.writerow(["encrypted_documents", data.get("encrypted_documents", 0)])
        writer.writerow(["unencrypted_documents", data.get("unencrypted_documents", 0)])
        writer.writerow(["active_keys", data.get("active_keys", 0)])
        writer.writerow(["inactive_keys", data.get("inactive_keys", 0)])
    elif report.report_type == "retention_compliance":
        writer.writerow(["metric", "value"])
        writer.writerow(["total_lifecycle_entries", data.get("total_lifecycle_entries", 0)])
        writer.writerow(["expired_documents", data.get("expired_documents", 0)])
        writer.writerow(["overdue_documents", data.get("overdue_documents", 0)])
        writer.writerow(["needs_review", data.get("needs_review", 0)])
        writer.writerow(["compliant", data.get("compliant", 0)])
    elif report.report_type == "permission_audit":
        writer.writerow(["username", "roles", "permissions"])
        for entry in entries:
            writer.writerow([
                entry.get("username", ""),
                ";".join(entry.get("roles", [])),
                ";".join(entry.get("permissions", [])),
            ])

    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="compliance_report_{report_id}.csv"'
        },
    )
