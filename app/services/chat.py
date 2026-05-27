import logging

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import chat_completion, generate_embeddings
from app.models.chat import ChatMessage, ChatSession
from app.services.vectordb import VectorDBService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, vectordb_service: VectorDBService | None = None) -> None:
        self.vectordb_service = vectordb_service or VectorDBService()

    async def create_session(
        self,
        db: AsyncSession,
        user_id: str,
        title: str,
        scope_type: str = "global",
        scope_id: int | None = None,
    ) -> ChatSession:
        """Create a new chat session."""
        session = ChatSession(
            user_id=user_id,
            title=title,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session

    async def get_sessions(
        self, db: AsyncSession, user_id: str, limit: int = 50
    ) -> list[dict]:
        """List user's chat sessions with message counts."""
        stmt = (
            select(
                ChatSession,
                func.count(ChatMessage.id).label("message_count"),
            )
            .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
            .where(ChatSession.user_id == user_id)
            .group_by(ChatSession.id)
            .order_by(ChatSession.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()
        sessions = []
        for row in rows:
            session = row[0]
            count = row[1]
            sessions.append({
                "id": session.id,
                "title": session.title,
                "scope_type": session.scope_type,
                "scope_id": session.scope_id,
                "created_at": session.created_at,
                "message_count": count,
            })
        return sessions

    async def get_messages(
        self, db: AsyncSession, session_id: str, user_id: str
    ) -> list[ChatMessage]:
        """Get all messages in a session (verifying user ownership)."""
        session = await self._get_user_session(db, session_id, user_id)
        if session is None:
            return []

        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def send_message(
        self,
        db: AsyncSession,
        session_id: str,
        user_id: str,
        message_text: str,
    ) -> tuple[ChatMessage | None, ChatSession | None]:
        """Send a message in a chat session and get an AI response.

        Returns a tuple of (assistant_message, session) or (None, None) if session not found.
        """
        session = await self._get_user_session(db, session_id, user_id)
        if session is None:
            return None, None

        # Save the user message
        user_message = ChatMessage(
            session_id=session_id,
            role="user",
            content=message_text,
        )
        db.add(user_message)
        await db.flush()

        # Build conversation history from session
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        result = await db.execute(stmt)
        all_messages = list(result.scalars().all())

        # Apply sliding window: limit to last 20 messages
        max_messages = 20
        windowed_messages = all_messages[-max_messages:]

        # Apply character budget: max 50,000 chars for combined content
        max_chars = 50000
        messages_for_llm = []
        total_chars = 0
        for msg in reversed(windowed_messages):
            msg_len = len(msg.content)
            if total_chars + msg_len > max_chars and messages_for_llm:
                break
            messages_for_llm.append({"role": msg.role, "content": msg.content})
            total_chars += msg_len
        messages_for_llm.reverse()

        # Perform scoped RAG search
        context, sources = self._perform_rag_search(session, message_text)

        # Call the LLM
        answer = chat_completion(messages=messages_for_llm, context=context)

        # Save the assistant message with sources
        assistant_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=answer,
            sources_json=sources if sources else None,
        )
        db.add(assistant_message)
        await db.flush()
        await db.refresh(assistant_message)
        await db.refresh(session)

        return assistant_message, session

    async def export_session(
        self, db: AsyncSession, session_id: str, user_id: str, format: str = "markdown"
    ) -> str | None:
        """Export a chat session as markdown."""
        session = await self._get_user_session(db, session_id, user_id)
        if session is None:
            return None

        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        result = await db.execute(stmt)
        messages = list(result.scalars().all())

        lines = [f"## Session: {session.title}\n"]
        for msg in messages:
            if msg.role == "user":
                lines.append(f"**User:** {msg.content}\n")
            else:
                lines.append(f"**Assistant:** {msg.content}\n")
            lines.append("---\n")

        return "\n".join(lines)

    async def delete_session(
        self, db: AsyncSession, session_id: str, user_id: str
    ) -> bool:
        """Delete a chat session and all its messages."""
        session = await self._get_user_session(db, session_id, user_id)
        if session is None:
            return False

        # Delete messages first (cascade should handle it, but be explicit)
        await db.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        await db.delete(session)
        await db.flush()
        return True

    async def _get_user_session(
        self, db: AsyncSession, session_id: str, user_id: str
    ) -> ChatSession | None:
        """Get a session verifying user ownership."""
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    def _perform_rag_search(
        self, session: ChatSession, query: str
    ) -> tuple[str, list[dict]]:
        """Perform RAG search scoped to the session's scope."""
        embeddings = generate_embeddings([query])
        query_embedding = embeddings[0]

        # Determine group_id filter based on scope
        group_id = None
        if session.scope_type == "group" and session.scope_id is not None:
            group_id = session.scope_id
        elif session.scope_type == "document" and session.scope_id is not None:
            # For document scope, we use group_id=None and filter results
            # The vectordb doesn't support doc_id filter directly in query,
            # so we search globally and filter
            group_id = None

        results = self.vectordb_service.search(
            query_embedding=query_embedding,
            group_id=group_id,
            top_k=5,
        )

        # For document scope, filter to only the specific document
        if session.scope_type == "document" and session.scope_id is not None:
            results = [r for r in results if r["doc_id"] == session.scope_id]

        # Build context and sources
        context_parts = []
        sources = []
        for item in results:
            context_parts.append(item["chunk_text"])
            sources.append({
                "doc_id": item["doc_id"],
                "chunk_text": item["chunk_text"],
                "score": item["score"],
            })

        context = "\n\n---\n\n".join(context_parts)
        return context, sources

    async def get_message_count(self, db: AsyncSession, session_id: str) -> int:
        """Get the number of messages in a session."""
        stmt = select(func.count(ChatMessage.id)).where(
            ChatMessage.session_id == session_id
        )
        result = await db.execute(stmt)
        return result.scalar_one()
