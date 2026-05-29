"""Org structure CRUD router - units, positions, grades, assignments, chart, history."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.user import (
    OrgChangeHistory,
    OrgGrade,
    OrgPosition,
    OrgUnit,
    OrgUnitType,
    OrgUserAssignment,
    OrgUserGrade,
    User,
)

router = APIRouter(prefix="/org", tags=["org"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── Schemas ───────────────────────────────────────────────────────────────────


class OrgUnitCreate(BaseModel):
    code: str
    name: str
    short_name: str | None = None
    type_id: str | None = None
    parent_id: str | None = None
    head_user_id: str | None = None
    description: str | None = None
    sort_order: int = 0


class OrgPositionCreate(BaseModel):
    unit_id: str
    position_code: str
    position_name: str
    grade_id: str | None = None
    is_head: bool = False
    max_occupants: int = 1
    description: str | None = None


class OrgGradeCreate(BaseModel):
    grade_code: str
    grade_name: str
    grade_level: int
    grade_category: str | None = None
    description: str | None = None
    min_salary: float | None = None
    max_salary: float | None = None


class OrgAssignmentCreate(BaseModel):
    user_id: str
    position_id: str
    unit_id: str
    assignment_type: str = "primary"
    is_primary: bool = True
    notes: str | None = None


# ── Pages ─────────────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def org_dashboard(request: Request, _user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "org/dashboard.html")


@router.get("/units")
async def org_units_page(request: Request, _user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "org/units.html")


@router.get("/positions")
async def org_positions_page(
    request: Request, _user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(request, "org/positions.html")


@router.get("/grades")
async def org_grades_page(request: Request, _user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "org/grades.html")


@router.get("/assignments")
async def org_assignments_page(
    request: Request, _user: User = Depends(get_current_user)
):
    return templates.TemplateResponse(request, "org/assignments.html")


@router.get("/chart")
async def org_chart_page(request: Request, _user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "org/chart.html")


@router.get("/history")
async def org_history_page(request: Request, _user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request, "org/history.html")


# ── API: Units ────────────────────────────────────────────────────────────────


@router.get("/api/unit-types")
async def list_unit_types(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgUnitType).order_by(OrgUnitType.sort_order)
    )
    types = result.scalars().all()
    return [
        {"id": t.id, "code": t.code, "name": t.name, "sort_order": t.sort_order}
        for t in types
    ]


@router.get("/api/units")
async def list_units(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OrgUnit).order_by(OrgUnit.sort_order))
    units = result.scalars().all()
    return [
        {
            "id": u.id,
            "code": u.code,
            "name": u.name,
            "short_name": u.short_name,
            "type_id": u.type_id,
            "parent_id": u.parent_id,
            "is_active": u.is_active,
            "sort_order": u.sort_order,
        }
        for u in units
    ]


@router.post("/api/units", status_code=201)
async def create_unit(
    data: OrgUnitCreate,
    _user: User = Depends(require_permission("org_units", "create")),
    db: AsyncSession = Depends(get_db),
):
    unit = OrgUnit(
        code=data.code,
        name=data.name,
        short_name=data.short_name,
        type_id=data.type_id,
        parent_id=data.parent_id,
        head_user_id=data.head_user_id,
        description=data.description,
        sort_order=data.sort_order,
    )
    db.add(unit)
    await db.flush()
    await db.refresh(unit)
    return {"id": unit.id, "code": unit.code, "name": unit.name}


@router.put("/api/units/{unit_id}")
async def update_unit(
    unit_id: str,
    data: OrgUnitCreate,
    _user: User = Depends(require_permission("org_units", "update")),
    db: AsyncSession = Depends(get_db),
):
    unit = await db.get(OrgUnit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    unit.code = data.code
    unit.name = data.name
    unit.short_name = data.short_name
    unit.type_id = data.type_id
    unit.parent_id = data.parent_id
    unit.head_user_id = data.head_user_id
    unit.description = data.description
    unit.sort_order = data.sort_order
    await db.flush()
    return {"id": unit.id, "code": unit.code, "name": unit.name}


@router.delete("/api/units/{unit_id}", status_code=204)
async def delete_unit(
    unit_id: str,
    _user: User = Depends(require_permission("org_units", "delete")),
    db: AsyncSession = Depends(get_db),
):
    unit = await db.get(OrgUnit, unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    await db.delete(unit)
    await db.flush()


# ── API: Positions ────────────────────────────────────────────────────────────


@router.get("/api/positions")
async def list_positions(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OrgPosition))
    positions = result.scalars().all()
    return [
        {
            "id": p.id,
            "unit_id": p.unit_id,
            "position_code": p.position_code,
            "position_name": p.position_name,
            "grade_id": p.grade_id,
            "is_head": p.is_head,
            "is_active": p.is_active,
        }
        for p in positions
    ]


@router.post("/api/positions", status_code=201)
async def create_position(
    data: OrgPositionCreate,
    _user: User = Depends(require_permission("org_positions", "create")),
    db: AsyncSession = Depends(get_db),
):
    position = OrgPosition(
        unit_id=data.unit_id,
        position_code=data.position_code,
        position_name=data.position_name,
        grade_id=data.grade_id,
        is_head=data.is_head,
        max_occupants=data.max_occupants,
        description=data.description,
    )
    db.add(position)
    await db.flush()
    await db.refresh(position)
    return {
        "id": position.id,
        "position_code": position.position_code,
        "position_name": position.position_name,
    }


@router.delete("/api/positions/{position_id}", status_code=204)
async def delete_position(
    position_id: str,
    _user: User = Depends(require_permission("org_positions", "delete")),
    db: AsyncSession = Depends(get_db),
):
    position = await db.get(OrgPosition, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    await db.delete(position)
    await db.flush()


# ── API: Grades ───────────────────────────────────────────────────────────────


@router.get("/api/grades")
async def list_grades(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OrgGrade).order_by(OrgGrade.grade_level))
    grades = result.scalars().all()
    return [
        {
            "id": g.id,
            "grade_code": g.grade_code,
            "grade_name": g.grade_name,
            "grade_level": g.grade_level,
            "grade_category": g.grade_category,
            "is_active": g.is_active,
        }
        for g in grades
    ]


@router.post("/api/grades", status_code=201)
async def create_grade(
    data: OrgGradeCreate,
    _user: User = Depends(require_permission("org_grades", "create")),
    db: AsyncSession = Depends(get_db),
):
    grade = OrgGrade(
        grade_code=data.grade_code,
        grade_name=data.grade_name,
        grade_level=data.grade_level,
        grade_category=data.grade_category,
        description=data.description,
        min_salary=data.min_salary,
        max_salary=data.max_salary,
    )
    db.add(grade)
    await db.flush()
    await db.refresh(grade)
    return {
        "id": grade.id,
        "grade_code": grade.grade_code,
        "grade_name": grade.grade_name,
    }


@router.delete("/api/grades/{grade_id}", status_code=204)
async def delete_grade(
    grade_id: str,
    _user: User = Depends(require_permission("org_grades", "delete")),
    db: AsyncSession = Depends(get_db),
):
    grade = await db.get(OrgGrade, grade_id)
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    await db.delete(grade)
    await db.flush()


# ── API: Assignments ──────────────────────────────────────────────────────────


@router.get("/api/assignments")
async def list_assignments(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgUserAssignment).where(OrgUserAssignment.is_active == True)  # noqa: E712
    )
    assignments = result.scalars().all()
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "position_id": a.position_id,
            "unit_id": a.unit_id,
            "assignment_type": a.assignment_type,
            "is_primary": a.is_primary,
            "is_active": a.is_active,
        }
        for a in assignments
    ]


@router.post("/api/assignments", status_code=201)
async def create_assignment(
    data: OrgAssignmentCreate,
    current_user: User = Depends(require_permission("org_assignments", "create")),
    db: AsyncSession = Depends(get_db),
):
    assignment = OrgUserAssignment(
        user_id=data.user_id,
        position_id=data.position_id,
        unit_id=data.unit_id,
        assignment_type=data.assignment_type,
        is_primary=data.is_primary,
        notes=data.notes,
        created_by=current_user.id,
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)
    return {"id": assignment.id, "user_id": assignment.user_id}


@router.delete("/api/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: str,
    _user: User = Depends(require_permission("org_assignments", "delete")),
    db: AsyncSession = Depends(get_db),
):
    assignment = await db.get(OrgUserAssignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    assignment.is_active = False
    await db.flush()


# ── API: Chart ────────────────────────────────────────────────────────────────


@router.get("/api/chart")
async def get_org_chart(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return org tree structure as nested JSON."""
    result = await db.execute(
        select(OrgUnit).where(OrgUnit.is_active == True).order_by(OrgUnit.sort_order)  # noqa: E712
    )
    units = result.scalars().all()

    unit_map = {u.id: {"id": u.id, "code": u.code, "name": u.name, "children": []} for u in units}
    roots = []
    for u in units:
        node = unit_map[u.id]
        if u.parent_id and u.parent_id in unit_map:
            unit_map[u.parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


# ── API: History ──────────────────────────────────────────────────────────────


@router.get("/api/history")
async def list_history(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgChangeHistory).order_by(OrgChangeHistory.changed_at.desc()).limit(100)
    )
    entries = result.scalars().all()
    return [
        {
            "id": h.id,
            "change_type": h.change_type,
            "target_type": h.target_type,
            "target_id": h.target_id,
            "changed_by": h.changed_by,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
        }
        for h in entries
    ]


# ── API: User Grades ─────────────────────────────────────────────────────────


@router.get("/api/user-grades/{user_id}")
async def list_user_grades(
    user_id: str,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgUserGrade).where(OrgUserGrade.user_id == user_id)
    )
    grades = result.scalars().all()
    return [
        {
            "id": g.id,
            "grade_id": g.grade_id,
            "effective_from": g.effective_from.isoformat() if g.effective_from else None,
            "effective_to": g.effective_to.isoformat() if g.effective_to else None,
            "is_current": g.is_current,
            "reason": g.reason,
        }
        for g in grades
    ]


# ── API: User Status & Auto-Reassignment ─────────────────────────────────────


from app.models.user import UserStatus
from app.services.auto_reassignment import AutoReassignmentService
from pydantic import BaseModel


class UserStatusUpdate(BaseModel):
    status: UserStatus
    reason: str | None = None


@router.put("/api/users/{user_id}/status", response_model=dict)
async def update_user_status(
    user_id: str,
    data: UserStatusUpdate,
    current_user: User = Depends(require_permission("users", "update")),
    db: AsyncSession = Depends(get_db),
):
    """
    Update user status and trigger automatic reassignment of tasks/responsibilities.
    
    When a user is marked as resigned/terminated/MIA, their:
    - Workflow tasks are reassigned to position replacements or escalated up
    - Org assignments are deactivated
    - Responsibilities escalate to higher structure (position head → parent unit head → admin)
    """
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    old_status = user.status
    user.status = data.status
    user.status_changed_at = func.now()
    user.status_changed_by = current_user.id
    
    if data.reason:
        # Store reason in notes or audit log
        pass
    
    # Trigger auto-reassignment service
    reassignment_service = AutoReassignmentService(db)
    reassignment_result = await reassignment_service.handle_user_status_change(
        user_id=user_id,
        new_status=data.status,
        changed_by=current_user.id
    )
    
    await db.flush()
    
    return {
        "success": True,
        "user_id": user_id,
        "old_status": old_status.value,
        "new_status": data.status.value,
        "reassignment": reassignment_result,
    }


@router.get("/api/users/mia-check", response_model=list[dict])
async def check_mia_users(
    days_threshold: int = 7,
    _user: User = Depends(require_permission("users", "read")),
    db: AsyncSession = Depends(get_db),
):
    """Check for users who haven't been seen in threshold days."""
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)
    
    result = await db.execute(
        select(User)
        .where(User.status == UserStatus.active)
        .where(User.last_seen_at != None)
        .where(User.last_seen_at < cutoff)
    )
    mia_candidates = result.scalars().all()
    
    return [
        {
            "id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "email": u.email,
            "last_seen": u.last_seen_at.isoformat() if u.last_seen_at else None,
            "days_inactive": (datetime.now(timezone.utc) - u.last_seen_at).days if u.last_seen_at else None,
        }
        for u in mia_candidates
    ]
