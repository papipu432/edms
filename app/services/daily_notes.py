"""Service for generating daily digest notes."""

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.llm import chat_completion
from app.models.document import Document, DocumentStatus
from app.models.lifecycle import DocumentLifecycle, DocumentLifecycleState

logger = logging.getLogger(__name__)


class DailyNotesService:
    """Generates and manages daily digest notes in the wiki."""

    def __init__(self, wiki_path: str | None = None) -> None:
        self.wiki_path = Path(wiki_path or settings.WIKI_PATH)

    async def generate_daily_note(self, db: AsyncSession) -> dict[str, str]:
        """Generate a daily note for today.

        Queries documents uploaded today, pending approvals, expiring documents,
        and recent activity. Uses LLM to generate a natural language summary.
        Stores at wiki_path/daily/YYYY-MM-DD.md.
        """
        today = date.today()
        today_str = today.isoformat()

        # Query documents uploaded today
        today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        docs_result = await db.execute(
            select(Document).where(
                Document.created_at >= today_start,
            )
        )
        uploaded_docs = docs_result.scalars().all()

        # Query pending approvals (documents in review state)
        pending_result = await db.execute(
            select(DocumentLifecycle).where(
                DocumentLifecycle.state == DocumentLifecycleState.in_review,
            )
        )
        pending_lifecycles = pending_result.scalars().all()

        # Query expiring documents
        expiring_result = await db.execute(
            select(DocumentLifecycle).where(
                DocumentLifecycle.state == DocumentLifecycleState.expired,
            )
        )
        expired_lifecycles = expiring_result.scalars().all()

        # Build context for LLM
        context_parts = [
            f"Date: {today_str}",
            f"Documents uploaded today: {len(uploaded_docs)}",
        ]

        if uploaded_docs:
            doc_names = [d.original_filename for d in uploaded_docs]
            context_parts.append(f"Uploaded files: {', '.join(doc_names)}")

        context_parts.append(f"Pending approvals: {len(pending_lifecycles)}")
        context_parts.append(f"Expired documents: {len(expired_lifecycles)}")

        context = "\n".join(context_parts)

        # Generate summary using LLM
        messages = [
            {
                "role": "user",
                "content": (
                    "Generate a brief daily digest note summarizing today's EDMS activity. "
                    "Include sections for new uploads, pending actions, and any alerts."
                ),
            }
        ]
        llm_summary = chat_completion(messages, context=context)

        # Build the daily note markdown
        note_content = (
            f"# Daily Note - {today_str}\n\n"
            f"## Summary\n\n{llm_summary}\n\n"
            f"## Documents Uploaded Today\n\n"
        )

        if uploaded_docs:
            for doc in uploaded_docs:
                note_content += f"- {doc.original_filename} (ID: {doc.id})\n"
        else:
            note_content += "- No documents uploaded today\n"

        note_content += f"\n## Pending Approvals\n\n"
        note_content += f"- {len(pending_lifecycles)} document(s) awaiting review\n"

        note_content += f"\n## Expired Documents\n\n"
        note_content += f"- {len(expired_lifecycles)} document(s) expired\n"

        # Store the note
        daily_dir = self.wiki_path / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        note_path = daily_dir / f"{today_str}.md"
        note_path.write_text(note_content, encoding="utf-8")

        return {
            "date": today_str,
            "path": f"daily/{today_str}.md",
            "content": note_content,
        }

    def list_daily_notes(self) -> list[dict[str, str]]:
        """List all existing daily notes."""
        daily_dir = self.wiki_path / "daily"
        if not daily_dir.exists():
            return []

        notes = []
        for f in sorted(daily_dir.iterdir(), reverse=True):
            if f.suffix == ".md":
                date_str = f.stem
                notes.append({"date": date_str, "path": f"daily/{f.name}"})

        return notes
