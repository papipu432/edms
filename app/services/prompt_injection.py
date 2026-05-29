"""Prompt injection detection utility with security alert logging."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import SecurityAlert
from app.services.prompt_guard import PromptGuard

logger = logging.getLogger(__name__)

_guard = PromptGuard()


async def sanitize_for_llm(
    text: str, source: str, db: AsyncSession | None = None
) -> str:
    """Sanitize user content for LLM consumption with optional alert logging.

    Args:
        text: The user-provided text to sanitize.
        source: Identifies the origin (e.g., 'document_content', 'chat_message').
        db: Optional async database session for logging SecurityAlert records.

    Returns:
        Sanitized and wrapped text safe for LLM consumption.
    """
    sanitized, detections = _guard.sanitize(text)

    if detections:
        logger.warning(
            "Prompt injection detected from source=%s: %d pattern(s) matched",
            source,
            len(detections),
        )

        if db is not None:
            for detection in detections:
                alert = SecurityAlert(
                    alert_type="prompt_injection",
                    severity=detection["severity"],
                    message=(
                        f"Prompt injection pattern '{detection['pattern_name']}' "
                        f"detected in {source}"
                    ),
                    details_json={
                        "source": source,
                        "pattern_name": detection["pattern_name"],
                        "matched_text": detection["matched_text"][:200],
                    },
                    source_path=source,
                )
                db.add(alert)
            await db.flush()

    wrapped = _guard.wrap_user_content(sanitized)
    return wrapped
