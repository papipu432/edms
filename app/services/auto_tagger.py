"""Auto-tagging service using LLM to generate document tags."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_chat_model, _sanitize_and_wrap, _llm_circuit_breaker, _DATA_ONLY_INSTRUCTION

logger = logging.getLogger(__name__)


def generate_tags(content: str) -> list[str]:
    """Generate 3-5 relevant tags from document content using LLM.

    Args:
        content: Sanitized markdown content of the document.

    Returns:
        List of tag name strings (3-5 tags), or empty list on failure.
    """
    model = get_chat_model()
    if model is None:
        return []

    def _invoke():
        wrapped_content = _sanitize_and_wrap(content[:4000])
        messages = [
            SystemMessage(
                content="Extract 3-5 concise topic tags from this document. "
                "Return only tag names, one per line. Do not number them or add any other text. "
                + _DATA_ONLY_INSTRUCTION
            ),
            HumanMessage(
                content=f"Generate tags for the following document:\n\n{wrapped_content}"
            ),
        ]
        result = model.invoke(messages)
        response_text = result.content or ""
        # Parse one tag per line
        tags = []
        for line in response_text.strip().splitlines():
            tag = line.strip().strip("-•*").strip()
            if tag:
                tags.append(tag[:100])  # Limit tag length to match model constraint
        return tags[:5]  # Return at most 5 tags

    result = _llm_circuit_breaker.call(_invoke, fallback=[])
    return result
