"""Form field extraction service using LLM to extract key-value pairs from documents."""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_chat_model, _sanitize_and_wrap, _llm_circuit_breaker, _DATA_ONLY_INSTRUCTION

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "Extract all key-value pairs, form fields, and structured data from this document as JSON. "
    "Return ONLY valid JSON with string keys and string values. No other text."
)


def extract_fields(content: str, extraction_prompt: str | None = None) -> dict:
    """Extract key-value pairs from document content using LLM.

    Args:
        content: Sanitized markdown content of the document.
        extraction_prompt: Optional custom extraction prompt (e.g., from a template).

    Returns:
        Dict of extracted field name-value pairs, or empty dict on failure.
    """
    model = get_chat_model()
    if model is None:
        return {}

    prompt = extraction_prompt or _DEFAULT_PROMPT

    def _invoke():
        wrapped_content = _sanitize_and_wrap(content[:4000])
        messages = [
            SystemMessage(
                content=prompt + " " + _DATA_ONLY_INSTRUCTION
            ),
            HumanMessage(
                content=f"Extract fields from the following document:\n\n{wrapped_content}"
            ),
        ]
        result = model.invoke(messages)
        response_text = (result.content or "").strip()
        # Strip markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])
        return json.loads(response_text)

    result = _llm_circuit_breaker.call(_invoke, fallback={})
    if not isinstance(result, dict):
        return {}
    return result
