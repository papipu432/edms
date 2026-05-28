"""Compliance reporting service."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import DocumentAuditLog
from app.models.document import Document
from app.models.encryption import EncryptionKey
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState
from app.models.user import Permission, Role, RolePermission, User, UserRole


class ComplianceReportService:
    """Service for generating compliance reports."""

    async def generate_access_log_report(
        self,
        db: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict:
        """Generate access log report grouped by actor and document."""
        query = select(
            DocumentAuditLog.actor_username,
            DocumentAuditLog.document_id,
            DocumentAuditLog.action,
            func.count().label("count"),
        ).group_by(
            DocumentAuditLog.actor_username,
            DocumentAuditLog.document_id,
            DocumentAuditLog.action,
        )

        if start_date:
            query = query.where(DocumentAuditLog.timestamp >= start_date)
        if end_date:
            query = query.where(DocumentAuditLog.timestamp <= end_date)

        result = await db.execute(query)
        rows = result.all()

        entries = []
        for row in rows:
            entries.append({
                "actor_username": row.actor_username,
                "document_id": row.document_id,
                "action": row.action,
                "count": row.count,
            })

        return {
            "report_type": "access_log",
            "total_entries": len(entries),
            "entries": entries,
        }

    async def generate_encryption_status_report(self, db: AsyncSession) -> dict:
        """Generate encryption status report for documents and keys."""
        # Count documents
        doc_count_result = await db.execute(select(func.count(Document.id)))
        total_docs = doc_count_result.scalar() or 0

        # Count encryption keys
        key_result = await db.execute(
            select(
                EncryptionKey.is_active,
                func.count().label("count"),
            ).group_by(EncryptionKey.is_active)
        )
        key_rows = key_result.all()

        active_keys = 0
        inactive_keys = 0
        for row in key_rows:
            if row.is_active:
                active_keys = row.count
            else:
                inactive_keys = row.count

        # Count documents with encrypted PDF paths
        encrypted_result = await db.execute(
            select(func.count(Document.id)).where(
                Document.encrypted_pdf_path.isnot(None)
            )
        )
        encrypted_docs = encrypted_result.scalar() or 0

        return {
            "report_type": "encryption_status",
            "total_documents": total_docs,
            "encrypted_documents": encrypted_docs,
            "unencrypted_documents": total_docs - encrypted_docs,
            "active_keys": active_keys,
            "inactive_keys": inactive_keys,
        }

    async def generate_retention_compliance_report(self, db: AsyncSession) -> dict:
        """Generate retention compliance report for documents past retention."""
        now = datetime.utcnow()

        # Documents that are expired
        expired_result = await db.execute(
            select(func.count(DocumentLifecycle.id)).where(
                DocumentLifecycle.state == DocumentLifecycleState.expired
            )
        )
        expired_count = expired_result.scalar() or 0

        # Documents past their expiry date but not in expired state
        overdue_result = await db.execute(
            select(func.count(DocumentLifecycle.id)).where(
                DocumentLifecycle.expires_at < now,
                DocumentLifecycle.state != DocumentLifecycleState.expired,
            )
        )
        overdue_count = overdue_result.scalar() or 0

        # Documents needing re-review
        needs_review_result = await db.execute(
            select(func.count(DocumentLifecycle.id)).where(
                DocumentLifecycle.state == DocumentLifecycleState.needs_re_review
            )
        )
        needs_review_count = needs_review_result.scalar() or 0

        # Total lifecycle entries
        total_result = await db.execute(
            select(func.count(DocumentLifecycle.id))
        )
        total_count = total_result.scalar() or 0

        return {
            "report_type": "retention_compliance",
            "total_lifecycle_entries": total_count,
            "expired_documents": expired_count,
            "overdue_documents": overdue_count,
            "needs_review": needs_review_count,
            "compliant": total_count - expired_count - overdue_count,
        }

    async def generate_permission_audit_report(self, db: AsyncSession) -> dict:
        """Generate permission audit report showing who has access to what."""
        result = await db.execute(
            select(
                User.username,
                Role.code.label("role_code"),
                Role.name.label("role_name"),
                Permission.resource,
                Permission.action,
            )
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
        )
        rows = result.all()

        # Group by user
        users_map: dict[str, dict] = {}
        for row in rows:
            if row.username not in users_map:
                users_map[row.username] = {
                    "username": row.username,
                    "roles": set(),
                    "permissions": set(),
                }
            users_map[row.username]["roles"].add(row.role_code)
            users_map[row.username]["permissions"].add(
                f"{row.resource}:{row.action}"
            )

        # Convert sets to lists for JSON serialization
        entries = []
        for user_data in users_map.values():
            entries.append({
                "username": user_data["username"],
                "roles": sorted(user_data["roles"]),
                "permissions": sorted(user_data["permissions"]),
            })

        return {
            "report_type": "permission_audit",
            "total_users_with_roles": len(entries),
            "entries": entries,
        }
