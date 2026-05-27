import json
import logging

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_chat_model() -> ChatOpenAI | None:
    """Return a ChatOpenAI model if API key is configured, otherwise None."""
    if not settings.OPENAI_API_KEY:
        return None
    return ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)


def get_llm_client() -> ChatOpenAI | None:
    """Backward-compatible function that returns a ChatOpenAI instance or None."""
    return get_chat_model()


def generate_summary(text: str) -> str:
    """Generate a summary of the given text using gpt-4o-mini.

    Returns a placeholder string if no API key is configured.
    """
    model = get_chat_model()
    if model is None:
        return "Summary not available (no API key configured)"

    try:
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful assistant that summarizes documents concisely.",
            ),
            (
                "human",
                "Please provide a concise summary of the following text:\n\n{text}",
            ),
        ])
        chain = prompt | model | StrOutputParser()
        return chain.invoke({"text": text[:4000]})
    except Exception as e:
        logger.error("Failed to generate summary: %s", e)
        return "Summary not available (generation failed)"


def extract_keywords(text: str) -> list[str]:
    """Extract keywords from the given text using gpt-4o-mini.

    Returns an empty list if no API key is configured.
    """
    model = get_chat_model()
    if model is None:
        return []

    try:
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a helpful assistant that extracts keywords from documents. "
                "Return keywords as a comma-separated list.",
            ),
            (
                "human",
                "Extract the main keywords from the following text:\n\n{text}",
            ),
        ])
        chain = prompt | model | StrOutputParser()
        content = chain.invoke({"text": text[:4000]})
        keywords = [k.strip() for k in content.split(",") if k.strip()]
        return keywords
    except Exception as e:
        logger.error("Failed to extract keywords: %s", e)
        return []


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using text-embedding-3-small.

    Returns zero vectors if no API key is configured.
    """
    if not settings.OPENAI_API_KEY:
        return [[0.0] * 1536 for _ in texts]

    try:
        embeddings_model = OpenAIEmbeddings(
            model="text-embedding-3-small", api_key=settings.OPENAI_API_KEY
        )
        return embeddings_model.embed_documents(texts)
    except Exception as e:
        logger.error("Failed to generate embeddings: %s", e)
        return [[0.0] * 1536 for _ in texts]


def chat_completion(messages: list, context: str) -> str:
    """Perform a RAG chat completion with provided context.

    Returns an error message if no API key is configured.
    """
    model = get_chat_model()
    if model is None:
        return "Chat is not available (no API key configured)"

    try:
        system_content = (
            "You are a helpful assistant that answers questions based on the provided context. "
            "Use the context below to answer the user's question. If the answer is not in the "
            "context, say so.\n\nContext:\n" + context
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_content}"),
            ("human", "{user_message}"),
        ])
        chain = prompt | model | StrOutputParser()
        # Extract user message from messages list
        user_message = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
        return chain.invoke({
            "system_content": system_content,
            "user_message": user_message,
        })
    except Exception as e:
        logger.error("Failed to complete chat: %s", e)
        return "Chat completion failed due to an error."


def extract_entities_topics(text: str) -> dict:
    """Use a LangChain chain to extract entities and topics as JSON.

    Returns a dict with 'entities' and 'topics' keys (lists of strings).
    """
    model = get_chat_model()
    if model is None:
        return {"entities": [], "topics": []}

    try:
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You extract structured information from text. Always return valid JSON.",
            ),
            (
                "human",
                "Extract key entities (people, organizations, technologies, places) "
                "and topics (concepts, themes, subjects) from the following text. "
                "Return a JSON object with two keys: 'entities' (list of strings) "
                "and 'topics' (list of strings). Return ONLY the JSON, no other text.\n\n"
                "Text:\n{text}",
            ),
        ])
        chain = prompt | model | StrOutputParser()
        result_text = chain.invoke({"text": text[:4000]})
        result_text = result_text.strip()
        if result_text.startswith("```"):
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])
        return json.loads(result_text)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("Failed to extract entities/topics: %s", e)
        return {"entities": [], "topics": []}


def merge_content(existing: str, new_info: str) -> str:
    """Use a LangChain chain to merge wiki content.

    Returns merged content as a string.
    """
    model = get_chat_model()
    if model is None:
        return existing + "\n\n" + new_info

    try:
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a wiki editor that merges information cleanly.",
            ),
            (
                "human",
                "You are updating a wiki page. Merge the new information into the existing page content. "
                "Keep the page well-organized and avoid duplicating information. "
                "Return ONLY the updated markdown content.\n\n"
                "Existing page:\n{existing}\n\n"
                "New information to integrate:\n{new_info}",
            ),
        ])
        chain = prompt | model | StrOutputParser()
        return chain.invoke({"existing": existing, "new_info": new_info})
    except Exception as e:
        logger.error("Failed to merge page content: %s", e)
        return existing + "\n\n" + new_info
