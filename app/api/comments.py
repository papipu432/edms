import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.comment import Comment
from app.models.document import Document
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentResponse, CommentUpdate
from app.services.notifications import get_notification_manager

router = APIRouter(tags=["comments"])

MENTION_PATTERN = re.compile(r"@(\w+)")


async def _resolve_mentions(content: str, db: AsyncSession) -> list[User]:
    """Parse @mentions from content and resolve to user objects."""
    usernames = MENTION_PATTERN.findall(content)
    if not usernames:
        return []
    result = await db.execute(
        select(User).where(User.username.in_(usernames))
    )
    return list(result.scalars().all())


async def _build_comment_response(comment: Comment, db: AsyncSession) -> CommentResponse:
    """Build a CommentResponse with username populated."""
    user = await db.get(User, comment.user_id)
    username = user.username if user else "unknown"
    return CommentResponse(
        id=comment.id,
        document_id=comment.document_id,
        user_id=comment.user_id,
        username=username,
        content=comment.content,
        parent_id=comment.parent_id,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.post(
    "/api/documents/{document_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
async def create_comment(
    document_id: int,
    data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    comment = Comment(
        document_id=document_id,
        user_id=current_user.id,
        content=data.content,
        parent_id=data.parent_id,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)

    # Handle @mentions
    mentioned_users = await _resolve_mentions(data.content, db)
    notification_manager = get_notification_manager()
    for mentioned_user in mentioned_users:
        if mentioned_user.id != current_user.id:
            await notification_manager.create_notification(
                db,
                mentioned_user.id,
                "mention",
                "You were mentioned",
                f"@{current_user.username} mentioned you in a comment on document #{document_id}.",
                {"document_id": document_id, "comment_id": comment.id},
            )

    return await _build_comment_response(comment, db)


@router.get(
    "/api/documents/{document_id}/comments",
    response_model=list[CommentResponse],
)
async def list_comments(
    document_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Intentionally unauthenticated - matches the pattern of the annotations list
    # endpoint which is also publicly accessible (see test_workflow.py).
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    result = await db.execute(
        select(Comment)
        .where(Comment.document_id == document_id)
        .order_by(Comment.created_at)
    )
    comments = list(result.scalars().all())
    responses = []
    for comment in comments:
        responses.append(await _build_comment_response(comment, db))
    return responses


@router.put(
    "/api/comments/{comment_id}",
    response_model=CommentResponse,
)
async def update_comment(
    comment_id: int,
    data: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comment = await db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot edit another user's comment")

    comment.content = data.content
    comment.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(comment)
    return await _build_comment_response(comment, db)


@router.delete(
    "/api/comments/{comment_id}",
    status_code=204,
)
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comment = await db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Allow deletion by owner or admin
    is_admin = "admin" in current_user.role_codes
    if comment.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Cannot delete another user's comment")

    await db.delete(comment)
    await db.flush()
