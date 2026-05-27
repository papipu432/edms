from pathlib import Path

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_document(client: AsyncClient, sample_pdf: Path):
    # Create a group first
    group_response = await client.post("/api/groups", json={"name": "Doc Group"})
    group_id = group_response.json()["id"]

    # Upload a PDF document
    with open(sample_pdf, "rb") as f:
        response = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("test.pdf", f, "application/pdf")},
        )
    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "test.pdf"
    assert data["group_id"] == group_id
    assert data["file_type"] == "application/pdf"
    assert data["status"] == "processing"
    assert data["file_size"] > 0


@pytest.mark.asyncio
async def test_upload_document_group_not_found(client: AsyncClient, sample_pdf: Path):
    with open(sample_pdf, "rb") as f:
        response = await client.post(
            "/api/groups/9999/documents",
            files={"file": ("test.pdf", f, "application/pdf")},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient, sample_pdf: Path):
    group_response = await client.post("/api/groups", json={"name": "List Group"})
    group_id = group_response.json()["id"]

    with open(sample_pdf, "rb") as f:
        await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("doc1.pdf", f, "application/pdf")},
        )

    response = await client.get("/api/documents")
    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_document(client: AsyncClient, sample_pdf: Path):
    group_response = await client.post("/api/groups", json={"name": "Get Doc Group"})
    group_id = group_response.json()["id"]

    with open(sample_pdf, "rb") as f:
        upload_response = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("get_test.pdf", f, "application/pdf")},
        )
    doc_id = upload_response.json()["id"]

    response = await client.get(f"/api/documents/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert data["original_filename"] == "get_test.pdf"


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient):
    response = await client.get("/api/documents/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_document(client: AsyncClient, sample_pdf: Path):
    group_response = await client.post(
        "/api/groups", json={"name": "Download Group"}
    )
    group_id = group_response.json()["id"]

    with open(sample_pdf, "rb") as f:
        upload_response = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("download_test.pdf", f, "application/pdf")},
        )
    doc_id = upload_response.json()["id"]

    response = await client.get(f"/api/documents/{doc_id}/download")
    assert response.status_code == 200
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_delete_document(client: AsyncClient, sample_pdf: Path):
    group_response = await client.post(
        "/api/groups", json={"name": "Delete Doc Group"}
    )
    group_id = group_response.json()["id"]

    with open(sample_pdf, "rb") as f:
        upload_response = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("delete_test.pdf", f, "application/pdf")},
        )
    doc_id = upload_response.json()["id"]

    response = await client.delete(f"/api/documents/{doc_id}")
    assert response.status_code == 204

    get_response = await client.get(f"/api/documents/{doc_id}")
    assert get_response.status_code == 404
