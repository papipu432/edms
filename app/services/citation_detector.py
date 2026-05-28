"""Citation detection service using LLM to identify document references."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_chat_model, _sanitize_and_wrap, _llm_circuit_breaker, _DATA_ONLY_INSTRUCTION

logger = logging.getLogger(__name__)


def detect_citations(content: str, documents: list[tuple[int, str]]) -> list[int]:
    """Detect which known documents are cited or referenced in the content.

    Args:
        content: Sanitized markdown content of the document.
        documents: List of (doc_id, doc_name) tuples representing known documents.

    Returns:
        List of target document IDs that are cited/referenced.
    """
    if not documents:
        return []

    model = get_chat_model()
    if model is None:
        return []

    def _invoke():
        wrapped_content = _sanitize_and_wrap(content[:4000])
        doc_list = "\n".join(f"ID:{doc_id} - {name}" for doc_id, name in documents)
        messages = [
            SystemMessage(
                content="Given a document's content and a list of known documents, identify which "
                "documents are cited or referenced in the content. Return ONLY the numeric document "
                "IDs, one per line. If none are referenced, return nothing. "
                + _DATA_ONLY_INSTRUCTION
            ),
            HumanMessage(
                content=f"Document content:\n{wrapped_content}\n\n"
                f"Known documents:\n{doc_list}\n\n"
                "Which document IDs are cited or referenced? Return only IDs, one per line."
            ),
        ]
        result = model.invoke(messages)
        response_text = result.content or ""
        # Parse document IDs from response
        cited_ids = []
        valid_ids = {doc_id for doc_id, _ in documents}
        for line in response_text.strip().splitlines():
            line = line.strip().strip("-•*").strip()
            # Extract numeric ID (might have "ID:" prefix)
            line = line.replace("ID:", "").strip()
            try:
                doc_id = int(line)
                if doc_id in valid_ids:
                    cited_ids.append(doc_id)
            except ValueError:
                continue
        return cited_ids

    result = _llm_circuit_breaker.call(_invoke, fallback=[])
    return result
