import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaService:
    """Service to interact with Ollama API for local LLM operations."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    async def list_models(self) -> list[dict]:
        """GET {base_url}/api/tags - returns list of model info."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
                return data.get("models", [])
        except httpx.ConnectError:
            logger.warning("Cannot connect to Ollama at %s", self.base_url)
            return []
        except Exception as e:
            logger.error("Failed to list Ollama models: %s", e)
            return []

    async def pull_model(self, model_name: str) -> dict:
        """POST {base_url}/api/pull - pull a model by name."""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_name},
                )
                resp.raise_for_status()
                return {"status": "success", "model": model_name}
        except httpx.ConnectError:
            logger.warning("Cannot connect to Ollama at %s", self.base_url)
            return {"status": "error", "detail": "Cannot connect to Ollama"}
        except Exception as e:
            logger.error("Failed to pull model %s: %s", model_name, e)
            return {"status": "error", "detail": str(e)}

    async def get_model_status(self, model_name: str) -> dict:
        """Check if a model is available locally."""
        models = await self.list_models()
        for model in models:
            if model.get("name", "").startswith(model_name):
                return {"available": True, "model": model}
        return {"available": False, "model": None}

    async def generate(self, model: str, prompt: str) -> str:
        """POST {base_url}/api/generate - generate a completion."""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("response", "")
        except httpx.ConnectError:
            logger.warning("Cannot connect to Ollama at %s", self.base_url)
            return ""
        except Exception as e:
            logger.error("Failed to generate with Ollama: %s", e)
            return ""

    async def embeddings(self, model: str, text: str) -> list[float]:
        """POST {base_url}/api/embeddings - generate embeddings."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": model, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("embedding", [])
        except httpx.ConnectError:
            logger.warning("Cannot connect to Ollama at %s", self.base_url)
            return []
        except Exception as e:
            logger.error("Failed to generate embeddings with Ollama: %s", e)
            return []

    async def check_connection(self) -> dict:
        """Check if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                return {"connected": True, "url": self.base_url}
        except httpx.ConnectError:
            return {"connected": False, "url": self.base_url, "error": "Connection refused"}
        except Exception as e:
            return {"connected": False, "url": self.base_url, "error": str(e)}
