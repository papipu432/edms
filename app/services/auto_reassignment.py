"""Automatic reassignment service for when users resign/terminate/MIA."""
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import (
    OrgUserAssignment,
    OrgPosition,
    OrgUnit,
    User,
    UserStatus,
)
from app.models.document import Document
from app.models.workflow import DocumentWorkflow, WorkflowStatus

logger = logging.getLogger(__name__)


class AutoReassignmentService:
    """
    Automatically reassigns tasks, approvals, and responsibilities
    when a user's status changes to resigned/terminated/MIA.
    
    Escalation hierarchy:
    1. Same position (if max_occupants > 1)
    2. Position head (if current user is not head)
    3. Parent unit head
    4. Grandparent unit head (recursive)
    5. System admin (fallback)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def handle_user_status_change(
        self, 
        user_id: str, 
        new_status: UserStatus,
        changed_by: Optional[str] = None
    ) -> dict:
        """
        Called when a user's status changes. Triggers reassignment logic.
        
        Returns dict with reassignment results.
        """
        logger.info(f"Handling status change for user {user_id} to {new_status.value}")
        
        user = await self.db.get(User, user_id)
        if not user:
            return {"error": "User not found"}
        
        # Get all active assignments for this user
        result = await self.db.execute(
            select(OrgUserAssignment)
            .where(OrgUserAssignment.user_id == user_id)
            .where(OrgUserAssignment.is_active == True)
        )
        assignments = result.scalars().all()
        
        reassigned_tasks = []
        reassigned_approvals = []
        
        # Reassign workflow tasks
        workflow_result = await self._reassign_workflow_tasks(user_id, new_status)
        reassigned_tasks.extend(workflow_result.get("reassigned", []))
        
        # For each org assignment, escalate to higher structure
        for assignment in assignments:
            escalation_result = await self._escalate_position_responsibilities(
                assignment, new_status
            )
            if escalation_result.get("success"):
                reassigned_approvals.append({
                    "position_id": assignment.position_id,
                    "unit_id": assignment.unit_id,
                    "escalated_to": escalation_result.get("escalated_to"),
                    "level": escalation_result.get("level")
                })
        
        # Deactivate user's org assignments
        for assignment in assignments:
            assignment.is_active = False
            assignment.effective_to = datetime.now(timezone.utc)
            assignment.notes = f"Deactivated due to user status: {new_status.value}"
        
        logger.info(
            f"Reassignment complete for user {user_id}: "
            f"{len(reassigned_tasks)} tasks, {len(reassigned_approvals)} positions"
        )
        
        return {
            "success": True,
            "user_id": user_id,
            "new_status": new_status.value,
            "reassigned_tasks": reassigned_tasks,
            "reassigned_approvals": reassigned_approvals,
            "deactivated_assignments": len(assignments)
        }

    async def _reassign_workflow_tasks(
        self, 
        user_id: str, 
        new_status: UserStatus
    ) -> dict:
        """Reassign workflow tasks from inactive user."""
        result = await self.db.execute(
            select(DocumentWorkflow)
            .where(DocumentWorkflow.assigned_to_user_id == user_id)
            .where(DocumentWorkflow.status.in_([
                WorkflowStatus.pending_review,
                WorkflowStatus.in_review,
                WorkflowStatus.pending_approval
            ]))
        )
        workflows = result.scalars().all()
        
        reassigned = []
        for wf in workflows:
            # Find replacement based on position hierarchy
            new_assignee_id = await self._find_replacement_for_position(
                wf.assigned_to_position_id
            )
            
            if new_assignee_id:
                wf.assigned_to_user_id = new_assignee_id
                wf.moved_at = datetime.now(timezone.utc)
                reassigned.append({
                    "document_id": wf.document_id,
                    "from_user": user_id,
                    "to_user": new_assignee_id,
                    "stage_id": wf.stage_id
                })
            else:
                # No replacement found, assign to admin
                admin = await self._get_system_admin()
                if admin:
                    wf.assigned_to_user_id = admin.id
                    reassigned.append({
                        "document_id": wf.document_id,
                        "from_user": user_id,
                        "to_user": admin.id,
                        "stage_id": wf.stage_id,
                        "fallback": True
                    })
        
        return {"reassigned": reassigned}

    async def _escalate_position_responsibilities(
        self,
        assignment: OrgUserAssignment,
        new_status: UserStatus
    ) -> dict:
        """
        Escalate responsibilities up the org hierarchy.
        
        Returns info about who responsibilities were escalated to.
        """
        position = await self.db.get(OrgPosition, assignment.position_id)
        if not position:
            return {"success": False, "error": "Position not found"}
        
        unit = await self.db.get(OrgUnit, assignment.unit_id)
        if not unit:
            return {"success": False, "error": "Unit not found"}
        
        # Level 1: Try same position (if multiple occupants allowed)
        if position.max_occupants > 1:
            other_occupant = await self._find_other_position_occupant(position.id)
            if other_occupant:
                return {
                    "success": True,
                    "escalated_to": other_occupant.id,
                    "level": "same_position"
                }
        
        # Level 2: Position head (if not already head)
        if not position.is_head:
            head = await self._find_position_head(unit.id)
            if head:
                return {
                    "success": True,
                    "escalated_to": head.user_id,
                    "level": "unit_head"
                }
        
        # Level 3+: Parent unit heads (recursive)
        current_unit = unit
        level = 0
        while current_unit.parent_id:
            level += 1
            parent_unit = await self.db.get(OrgUnit, current_unit.parent_id)
            if not parent_unit:
                break
            
            parent_head = await self._find_position_head(parent_unit.id)
            if parent_head and parent_head.is_active:
                return {
                    "success": True,
                    "escalated_to": parent_head.user_id,
                    "level": f"parent_unit_{level}"
                }
            current_unit = parent_unit
        
        # Fallback: System admin
        admin = await self._get_system_admin()
        if admin:
            return {
                "success": True,
                "escalated_to": admin.id,
                "level": "system_admin_fallback"
            }
        
        return {"success": False, "error": "No escalation target found"}

    async def _find_other_position_occupant(
        self, 
        position_id: str
    ) -> Optional[User]:
        """Find another active occupant of the same position."""
        result = await self.db.execute(
            select(OrgUserAssignment)
            .where(OrgUserAssignment.position_id == position_id)
            .where(OrgUserAssignment.is_active == True)
        )
        assignments = result.scalars().all()
        
        for assignment in assignments:
            user = await self.db.get(User, assignment.user_id)
            if user and user.status == UserStatus.active:
                return user
        return None

    async def _find_position_head(self, unit_id: str) -> Optional[OrgUserAssignment]:
        """Find the head of a unit."""
        result = await self.db.execute(
            select(OrgUserAssignment)
            .join(OrgPosition)
            .where(OrgUserAssignment.unit_id == unit_id)
            .where(OrgUserAssignment.is_active == True)
            .where(OrgPosition.is_head == True)
        )
        assignment = result.scalars().first()
        return assignment

    async def _find_replacement_for_position(
        self, 
        position_id: Optional[str]
    ) -> Optional[str]:
        """Find a replacement user for a position."""
        if not position_id:
            return None
        
        result = await self.db.execute(
            select(OrgUserAssignment)
            .where(OrgUserAssignment.position_id == position_id)
            .where(OrgUserAssignment.is_active == True)
        )
        assignments = result.scalars().all()
        
        for assignment in assignments:
            user = await self.db.get(User, assignment.user_id)
            if user and user.status == UserStatus.active:
                return user.id
        return None

    async def _get_system_admin(self) -> Optional[User]:
        """Get a system admin user as fallback."""
        from app.models.user import UserRole, Role
        result = await self.db.execute(
            select(User)
            .join(UserRole)
            .join(Role)
            .where(Role.code == "admin")
            .where(User.status == UserStatus.active)
            .limit(1)
        )
        return result.scalars().first()

    async def check_mia_users(
        self, 
        days_threshold: int = 7
    ) -> list[dict]:
        """
        Check for users who haven't been seen in threshold days.
        Can be scheduled to run periodically.
        """
        from sqlalchemy import func
        cutoff = datetime.now(timezone.utc)
        
        result = await self.db.execute(
            select(User)
            .where(User.status == UserStatus.active)
            .where(User.last_seen_at < cutoff)
        )
        mia_candidates = result.scalars().all()
        
        flagged = []
        for user in mia_candidates:
            flagged.append({
                "user_id": user.id,
                "username": user.username,
                "last_seen": user.last_seen_at.isoformat() if user.last_seen_at else None,
                "days_inactive": (datetime.now(timezone.utc) - user.last_seen_at).days if user.last_seen_at else None
            })
        
        return flagged
