from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.models.user import Role, User, UserRole


@pytest.fixture(autouse=True)
def _reset_llm_settings():
    """Reset LLM settings before and after each test."""
    original_provider = settings.LLM_PROVIDER
    original_url = settings.OLLAMA_BASE_URL
    original_summarize = settings.OLLAMA_MODEL_SUMMARIZE
    original_keywords = settings.OLLAMA_MODEL_KEYWORDS
    original_embeddings = settings.OLLAMA_MODEL_EMBEDDINGS
    original_chat = settings.OLLAMA_MODEL_CHAT
    yield
    settings.LLM_PROVIDER = original_provider
    settings.OLLAMA_BASE_URL = original_url
    settings.OLLAMA_MODEL_SUMMARIZE = original_summarize
    settings.OLLAMA_MODEL_KEYWORDS = original_keywords
    settings.OLLAMA_MODEL_EMBEDDINGS = original_embeddings
    settings.OLLAMA_MODEL_CHAT = original_chat


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed roles into the test database."""
    roles_data = [
        ("admin", "Administrator"),
        ("manager", "Manager"),
        ("viewer", "Viewer"),
    ]
    for code, name in roles_data:
        db_session.add(Role(code=code, name=name, description=f"{code} role", is_system=True))
    await db_session.flush()
    return db_session


@pytest_asyncio.fixture
async def admin_user(seeded_db):
    """Create an admin user in the test database."""
    result = await seeded_db.execute(select(Role).where(Role.code == "admin"))
    admin_role = result.scalar_one()

    user = User(
        username="admin",
        email="admin@edms.local",
        display_name="Admin",
        hashed_password=hash_password("admin"),
    )
    seeded_db.add(user)
    await seeded_db.flush()
    await seeded_db.refresh(user)

    user_role = UserRole(user_id=user.id, role_id=admin_role.id)
    seeded_db.add(user_role)
    await seeded_db.flush()
    await seeded_db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user):
    """Create a valid JWT token for the admin user."""
    return create_access_token(data={"sub": admin_user.username})


async def test_settings_llm_page_loads(client: AsyncClient, admin_token: str):
    """Test that the LLM settings HTML page loads successfully."""
    resp = await client.get(
        "/settings/llm",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert "LLM Settings" in resp.text
    assert "LLM Provider" in resp.text


async def test_settings_llm_page_requires_auth(client: AsyncClient):
    """Test that the settings page requires authentication."""
    resp = await client.get("/settings/llm")
    assert resp.status_code == 401


async def test_get_llm_config(client: AsyncClient, admin_token: str):
    """Test that the config endpoint returns current LLM config."""
    resp = await client.get(
        "/api/settings/llm",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "llm_provider" in data
    assert "ollama_base_url" in data
    assert "ollama_model_summarize" in data
    assert "ollama_model_keywords" in data
    assert "ollama_model_embeddings" in data
    assert "ollama_model_chat" in data


async def test_update_llm_config(client: AsyncClient, admin_token: str):
    """Test updating LLM configuration."""
    resp = await client.post(
        "/api/settings/llm",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "llm_provider": "ollama",
            "ollama_base_url": "http://myhost:11434",
            "ollama_model_summarize": "llama3.2",
            "ollama_model_chat": "llama3.2",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Verify the settings were updated
    resp = await client.get(
        "/api/settings/llm",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    data = resp.json()
    assert data["llm_provider"] == "ollama"
    assert data["ollama_base_url"] == "http://myhost:11434"
    assert data["ollama_model_summarize"] == "llama3.2"
    assert data["ollama_model_chat"] == "llama3.2"


async def test_update_llm_config_invalid_provider(client: AsyncClient, admin_token: str):
    """Test that invalid provider is rejected."""
    resp = await client.post(
        "/api/settings/llm",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"llm_provider": "invalid"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


@patch("app.services.ollama.OllamaService.list_models")
async def test_list_models_success(mock_list_models, client: AsyncClient, admin_token: str):
    """Test model list endpoint with mocked Ollama response."""
    mock_list_models.return_value = [
        {"name": "llama3.2:latest", "size": 4_000_000_000, "modified_at": "2024-01-01T00:00:00Z"},
        {"name": "nomic-embed-text:latest", "size": 500_000_000, "modified_at": "2024-01-02T00:00:00Z"},
    ]

    resp = await client.get(
        "/api/settings/llm/models",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert len(data["models"]) == 2
    assert data["models"][0]["name"] == "llama3.2:latest"


@patch("app.services.ollama.OllamaService.list_models")
async def test_list_models_connection_error(mock_list_models, client: AsyncClient, admin_token: str):
    """Test graceful error when Ollama is unreachable."""
    mock_list_models.return_value = []

    resp = await client.get(
        "/api/settings/llm/models",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["models"] == []


@patch("app.services.ollama.OllamaService.pull_model")
async def test_pull_model_success(mock_pull_model, client: AsyncClient, admin_token: str):
    """Test pull model endpoint with mocked Ollama response."""
    mock_pull_model.return_value = {"status": "success", "model": "llama3.2"}

    resp = await client.post(
        "/api/settings/llm/pull",
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
        json={"model": "llama3.2"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"


async def test_pull_model_empty_name(client: AsyncClient, admin_token: str):
    """Test pull model with empty name returns error."""
    resp = await client.post(
        "/api/settings/llm/pull",
        headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
        json={"model": ""},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"


@patch("app.services.ollama.OllamaService.check_connection")
async def test_ollama_status_connected(mock_check, client: AsyncClient, admin_token: str):
    """Test status endpoint when Ollama is connected."""
    mock_check.return_value = {"connected": True, "url": "http://localhost:11434"}

    resp = await client.get(
        "/api/settings/llm/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True


@patch("app.services.ollama.OllamaService.check_connection")
async def test_ollama_status_disconnected(mock_check, client: AsyncClient, admin_token: str):
    """Test status endpoint when Ollama is not reachable."""
    mock_check.return_value = {"connected": False, "url": "http://localhost:11434", "error": "Connection refused"}

    resp = await client.get(
        "/api/settings/llm/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
