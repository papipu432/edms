import logging

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_llm_client() -> OpenAI | None:
    """Return an OpenAI client if API key is configured, otherwise None."""
    if not settings.OPENAI_API_KEY:
        return None
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_summary(text: str) -> str:
    """Generate a summary of the given text using gpt-4o-mini.

    Returns a placeholder string if no API key is configured.
    """
    client = get_llm_client()
    if client is None:
        return "Summary not available (no API key configured)"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that summarizes documents concisely.",
                },
                {
                    "role": "user",
                    "content": f"Please provide a concise summary of the following text:\n\n{text[:4000]}",
                },
            ],
            max_tokens=500,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("Failed to generate summary: %s", e)
        return "Summary not available (generation failed)"


def extract_keywords(text: str) -> list[str]:
    """Extract keywords from the given text using gpt-4o-mini.

    Returns an empty list if no API key is configured.
    """
    client = get_llm_client()
    if client is None:
        return []

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful assistant that extracts keywords from documents. "
                        "Return keywords as a comma-separated list."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Extract the main keywords from the following text:\n\n{text[:4000]}",
                },
            ],
            max_tokens=200,
        )
        content = response.choices[0].message.content or ""
        keywords = [k.strip() for k in content.split(",") if k.strip()]
        return keywords
    except Exception as e:
        logger.error("Failed to extract keywords: %s", e)
        return []


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using text-embedding-3-small.

    Returns zero vectors if no API key is configured.
    """
    client = get_llm_client()
    if client is None:
        return [[0.0] * 1536 for _ in texts]

    try:
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        logger.error("Failed to generate embeddings: %s", e)
        return [[0.0] * 1536 for _ in texts]


def chat_completion(messages: list, context: str) -> str:
    """Perform a RAG chat completion with provided context.

    Returns an error message if no API key is configured.
    """
    client = get_llm_client()
    if client is None:
        return "Chat is not available (no API key configured)"

    try:
        system_message = {
            "role": "system",
            "content": (
                "You are a helpful assistant that answers questions based on the provided context. "
                "Use the context below to answer the user's question. If the answer is not in the "
                "context, say so.\n\nContext:\n" + context
            ),
        }
        all_messages = [system_message] + messages
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=all_messages,
            max_tokens=1000,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("Failed to complete chat: %s", e)
        return "Chat completion failed due to an error."
