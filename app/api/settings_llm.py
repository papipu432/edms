from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.core.config import settings
from app.core.security import require_permission
from app.models.user import User
from app.services.ollama import OllamaService

router = APIRouter(tags=["settings-llm"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


class LLMConfigUpdate(BaseModel):
    llm_provider: str | None = None
    ollama_base_url: str | None = None
    ollama_model_summarize: str | None = None
    ollama_model_keywords: str | None = None
    ollama_model_embeddings: str | None = None
    ollama_model_chat: str | None = None


@router.get("/settings/llm")
async def settings_llm_page(
    request: Request,
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Render the LLM settings HTML page."""
    return templates.TemplateResponse(request, "settings_llm.html")


@router.get("/api/settings/llm")
async def get_llm_config(
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Return current LLM configuration as JSON."""
    return {
        "llm_provider": settings.LLM_PROVIDER,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "ollama_model_summarize": settings.OLLAMA_MODEL_SUMMARIZE,
        "ollama_model_keywords": settings.OLLAMA_MODEL_KEYWORDS,
        "ollama_model_embeddings": settings.OLLAMA_MODEL_EMBEDDINGS,
        "ollama_model_chat": settings.OLLAMA_MODEL_CHAT,
    }


@router.post("/api/settings/llm")
async def update_llm_config(
    config: LLMConfigUpdate,
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Update LLM configuration (runtime only, not persisted to env file)."""
    if config.llm_provider is not None:
        if config.llm_provider not in ("openai", "ollama"):
            return {"status": "error", "detail": "Invalid provider. Must be 'openai' or 'ollama'."}
        settings.LLM_PROVIDER = config.llm_provider
    if config.ollama_base_url is not None:
        settings.OLLAMA_BASE_URL = config.ollama_base_url
    if config.ollama_model_summarize is not None:
        settings.OLLAMA_MODEL_SUMMARIZE = config.ollama_model_summarize
    if config.ollama_model_keywords is not None:
        settings.OLLAMA_MODEL_KEYWORDS = config.ollama_model_keywords
    if config.ollama_model_embeddings is not None:
        settings.OLLAMA_MODEL_EMBEDDINGS = config.ollama_model_embeddings
    if config.ollama_model_chat is not None:
        settings.OLLAMA_MODEL_CHAT = config.ollama_model_chat
    return {"status": "ok"}


@router.get("/api/settings/llm/models")
async def list_ollama_models(
    _user: User = Depends(require_permission("settings", "manage")),
):
    """List models available in Ollama."""
    service = OllamaService()
    models = await service.list_models()
    return {"models": models}


@router.post("/api/settings/llm/pull")
async def pull_ollama_model(
    request: Request,
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Pull a model from Ollama registry."""
    body = await request.json()
    model_name = body.get("model", "")
    if not model_name:
        return {"status": "error", "detail": "Model name is required"}
    service = OllamaService()
    result = await service.pull_model(model_name)
    return result


@router.get("/api/settings/llm/status")
async def ollama_status(
    _user: User = Depends(require_permission("settings", "manage")),
):
    """Check Ollama connection status."""
    service = OllamaService()
    return await service.check_connection()
