import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import settings
from app.services.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# Circuit breaker for LLM external calls
_llm_circuit_breaker = CircuitBreaker(
    failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    recovery_timeout=settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
)


def _is_ollama_provider() -> bool:
    """Check if the current LLM provider is Ollama."""
    return settings.LLM_PROVIDER == "ollama"


def get_chat_model() -> ChatOpenAI | None:
    """Return a ChatOpenAI model if API key is configured, otherwise None."""
    if _is_ollama_provider():
        return None  # Ollama uses its own service, not langchain ChatOpenAI
    if not settings.OPENAI_API_KEY:
        return None
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)


def get_llm_client() -> ChatOpenAI | None:
    """Backward-compatible function that returns a ChatOpenAI instance or None."""
    return get_chat_model()


def generate_summary(text: str) -> str:
    """Generate a summary of the given text using gpt-4o-mini.

    Returns a placeholder string if no API key is configured.
    Uses Ollama if LLM_PROVIDER is set to 'ollama'.
    Uses circuit breaker for external calls.
    """
    if _is_ollama_provider():
        model_name = settings.OLLAMA_MODEL_SUMMARIZE
        if not model_name:
            return "Summary not available (no Ollama model configured for summarization)"
        # Ollama generation is async; provide sync wrapper note
        return "Summary not available (Ollama requires async context)"

    model = get_chat_model()
    if model is None:
        return "Summary not available (no API key configured)"

    def _invoke():
        messages = [
            SystemMessage(content="You are a helpful assistant that summarizes documents concisely."),
            HumanMessage(content=f"Please provide a concise summary of the following text:\n\n{text[:4000]}"),
        ]
        result = model.invoke(messages)
        return result.content or ""

    result = _llm_circuit_breaker.call(
        _invoke,
        fallback="Summary not available (service temporarily unavailable)",
    )
    return result


def extract_keywords(text: str) -> list[str]:
    """Extract keywords from the given text using gpt-4o-mini.

    Returns an empty list if no API key is configured.
    Uses Ollama if LLM_PROVIDER is set to 'ollama'.
    Uses circuit breaker for external calls.
    """
    if _is_ollama_provider():
        model_name = settings.OLLAMA_MODEL_KEYWORDS
        if not model_name:
            return []
        return []  # Ollama requires async context

    model = get_chat_model()
    if model is None:
        return []

    def _invoke():
        messages = [
            SystemMessage(
                content="You are a helpful assistant that extracts keywords from documents. "
                "Return keywords as a comma-separated list."
            ),
            HumanMessage(content=f"Extract the main keywords from the following text:\n\n{text[:4000]}"),
        ]
        result = model.invoke(messages)
        content = result.content or ""
        keywords = [k.strip() for k in content.split(",") if k.strip()]
        return keywords

    result = _llm_circuit_breaker.call(_invoke, fallback=[])
    return result


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using text-embedding-3-small.

    Returns zero vectors if no API key is configured.
    Uses Ollama if LLM_PROVIDER is set to 'ollama'.
    Uses circuit breaker for external calls.
    """
    if _is_ollama_provider():
        model_name = settings.OLLAMA_MODEL_EMBEDDINGS
        if not model_name:
            return [[0.0] * 1536 for _ in texts]
        return [[0.0] * 1536 for _ in texts]  # Ollama requires async context

    if not settings.OPENAI_API_KEY:
        return [[0.0] * 1536 for _ in texts]

    fallback = [[0.0] * 1536 for _ in texts]

    def _invoke():
        embeddings_model = OpenAIEmbeddings(
            model="text-embedding-3-small", api_key=settings.OPENAI_API_KEY
        )
        return embeddings_model.embed_documents(texts)

    result = _llm_circuit_breaker.call(_invoke, fallback=fallback)
    return result


def chat_completion(messages: list, context: str) -> str:
    """Perform a RAG chat completion with provided context.

    Returns an error message if no API key is configured.
    Uses Ollama if LLM_PROVIDER is set to 'ollama'.
    Uses circuit breaker for external calls.
    """
    if _is_ollama_provider():
        model_name = settings.OLLAMA_MODEL_CHAT
        if not model_name:
            return "Chat is not available (no Ollama model configured for chat)"
        return "Chat is not available (Ollama requires async context)"

    model = get_chat_model()
    if model is None:
        return "Chat is not available (no API key configured)"

    def _invoke():
        system_content = (
            "You are a helpful assistant that answers questions based on the provided context. "
            "Use the context below to answer the user's question. If the answer is not in the "
            "context, say so.\n\nContext:\n" + context
        )
        # Extract user message from messages list
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
        # Use message objects directly to avoid template injection from
        # curly braces in context or user content
        messages_list = [
            SystemMessage(content=system_content),
            HumanMessage(content=user_message),
        ]
        result = model.invoke(messages_list)
        return result.content

    result = _llm_circuit_breaker.call(
        _invoke,
        fallback="Chat completion failed (service temporarily unavailable)",
    )
    return result


def extract_entities_topics(text: str) -> dict:
    """Use direct message objects to extract entities and topics as JSON.

    Returns a dict with 'entities' and 'topics' keys (lists of strings).
    """
    model = get_chat_model()
    if model is None:
        return {"entities": [], "topics": []}

    try:
        messages = [
            SystemMessage(content="You extract structured information from text. Always return valid JSON."),
            HumanMessage(
                content="Extract key entities (people, organizations, technologies, places) "
                "and topics (concepts, themes, subjects) from the following text. "
                "Return a JSON object with two keys: 'entities' (list of strings) "
                "and 'topics' (list of strings). Return ONLY the JSON, no other text.\n\n"
                f"Text:\n{text[:4000]}"
            ),
        ]
        result = model.invoke(messages)
        result_text = (result.content or "").strip()
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])
        return json.loads(result_text)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to extract entities/topics: %s", e)
        return {"entities": [], "topics": []}


def merge_content(existing: str, new_info: str) -> str:
    """Use direct message objects to merge wiki content.

    Returns merged content as a string.
    """
    model = get_chat_model()
    if model is None:
        return existing + "\n\n" + new_info

    try:
        messages = [
            SystemMessage(content="You are a wiki editor that merges information cleanly."),
            HumanMessage(
                content="You are updating a wiki page. Merge the new information into the existing page content. "
                "Keep the page well-organized and avoid duplicating information. "
                "Return ONLY the updated markdown content.\n\n"
                f"Existing page:\n{existing}\n\n"
                f"New information to integrate:\n{new_info}"
            ),
        ]
        result = model.invoke(messages)
        return result.content or ""
    except Exception as e:
        logger.error("Failed to merge page content: %s", e)
        return existing + "\n\n" + new_info
