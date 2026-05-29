import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_page(client: AsyncClient):
    response = await client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Login" in response.text


@pytest.mark.asyncio
async def test_root_page(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_dashboard_page(client: AsyncClient):
    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_workflow_page(client: AsyncClient):
    response = await client.get("/workflow")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_admin_page(client: AsyncClient):
    response = await client.get("/admin/users")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_document_viewer_page(client: AsyncClient):
    response = await client.get("/documents/1/view")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_crossref_page(client: AsyncClient):
    response = await client.get("/documents/1/crossref")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_register_page(client: AsyncClient):
    response = await client.get("/register")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Register" in response.text
