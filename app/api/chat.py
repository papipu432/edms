import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import (
    ChatExportResponse,
    ChatMessageResponse,
    ChatSendRequest,
    ChatSendResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)
from app.services.chat import ChatService
from app.services.prompt_injection import sanitize_for_llm

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

chat_service = ChatService()


@router.post("/api/chat/sessions", response_model=ChatSessionResponse)
async def create_session(
    request: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSessionResponse:
    """Create a new chat session."""
    session = await chat_service.create_session(
        db=db,
        user_id=current_user.id,
        title=request.title,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
    )
    return ChatSessionResponse(
        id=session.id,
        title=session.title,
        scope_type=session.scope_type,
        scope_id=session.scope_id,
        created_at=session.created_at,
        message_count=0,
    )


@router.get("/api/chat/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatSessionResponse]:
    """List the current user's chat sessions."""
    sessions = await chat_service.get_sessions(db=db, user_id=current_user.id)
    return [ChatSessionResponse(**s) for s in sessions]


@router.get("/api/chat/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ChatMessageResponse]:
    """Get all messages in a chat session."""
    messages = await chat_service.get_messages(
        db=db, session_id=session_id, user_id=current_user.id
    )
    if not messages and not await _session_exists(db, session_id, current_user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    return [
        ChatMessageResponse(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            sources=msg.sources_json,
            created_at=msg.created_at,
        )
        for msg in messages
    ]


@router.post("/api/chat/sessions/{session_id}/messages", response_model=ChatSendResponse)
async def send_message(
    session_id: str,
    request: ChatSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatSendResponse:
    """Send a message in a chat session and get an AI response."""
    # Sanitize the user message for prompt injection before passing to LLM
    await sanitize_for_llm(request.message, source="chat_message", db=db)

    assistant_message, session = await chat_service.send_message(
        db=db,
        session_id=session_id,
        user_id=current_user.id,
        message_text=request.message,
    )
    if assistant_message is None or session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    message_count = await chat_service.get_message_count(db=db, session_id=session_id)

    return ChatSendResponse(
        message=ChatMessageResponse(
            id=assistant_message.id,
            role=assistant_message.role,
            content=assistant_message.content,
            sources=assistant_message.sources_json,
            created_at=assistant_message.created_at,
        ),
        session=ChatSessionResponse(
            id=session.id,
            title=session.title,
            scope_type=session.scope_type,
            scope_id=session.scope_id,
            created_at=session.created_at,
            message_count=message_count,
        ),
    )


@router.get("/api/chat/sessions/{session_id}/export", response_model=ChatExportResponse)
async def export_session(
    session_id: str,
    format: str = Query(default="markdown", pattern="^(markdown)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatExportResponse:
    """Export a chat session as markdown."""
    content = await chat_service.export_session(
        db=db, session_id=session_id, user_id=current_user.id, format=format
    )
    if content is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return ChatExportResponse(format=format, content=content)


@router.delete("/api/chat/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a chat session and all its messages."""
    deleted = await chat_service.delete_session(
        db=db, session_id=session_id, user_id=current_user.id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"detail": "Session deleted"}


async def _session_exists(db: AsyncSession, session_id: str, user_id: str) -> bool:
    """Check if a session exists for the user."""
    from sqlalchemy import select
    from app.models.chat import ChatSession

    stmt = select(ChatSession.id).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None
