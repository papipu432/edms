from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(tags=["onboarding"])


@router.get("/api/onboarding/status")
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
):
    return {"completed": current_user.onboarding_completed}


@router.post("/api/onboarding/complete")
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.onboarding_completed = True
    await db.commit()
    return {"completed": True}
