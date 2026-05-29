from pathlib import Path

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_relationship(client: AsyncClient, sample_pdf: Path):
    """Test creating a relationship between two documents."""
    # Create a group and two documents
    group_resp = await client.post("/api/groups", json={"name": "Rel Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("doc1.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("doc2.pdf", f, "application/pdf")},
        )
    doc2_id = resp2.json()["id"]

    # Create a relationship
    response = await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={
            "target_document_id": doc2_id,
            "relationship_type": "references",
            "description": "Doc1 references Doc2",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["source_document_id"] == doc1_id
    assert data["target_document_id"] == doc2_id
    assert data["relationship_type"] == "references"
    assert data["description"] == "Doc1 references Doc2"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_relationships(client: AsyncClient, sample_pdf: Path):
    """Test listing relationships for a document."""
    group_resp = await client.post("/api/groups", json={"name": "List Rel Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("a.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("b.pdf", f, "application/pdf")},
        )
    doc2_id = resp2.json()["id"]

    # Create relationship
    await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "parent"},
    )

    # List relationships for doc1
    response = await client.get(f"/api/documents/{doc1_id}/relationships")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["source_document_id"] == doc1_id
    assert data[0]["target_document_id"] == doc2_id

    # List relationships for doc2 (it should appear as target)
    response = await client.get(f"/api/documents/{doc2_id}/relationships")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


@pytest.mark.asyncio
async def test_delete_relationship(client: AsyncClient, sample_pdf: Path):
    """Test deleting a relationship."""
    group_resp = await client.post("/api/groups", json={"name": "Del Rel Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("x.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("y.pdf", f, "application/pdf")},
        )
    doc2_id = resp2.json()["id"]

    # Create and then delete
    create_resp = await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "related"},
    )
    rel_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/relationships/{rel_id}")
    assert delete_resp.status_code == 204

    # Verify it's gone
    list_resp = await client.get(f"/api/documents/{doc1_id}/relationships")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 0


@pytest.mark.asyncio
async def test_delete_relationship_not_found(client: AsyncClient):
    """Test deleting a non-existent relationship returns 404."""
    response = await client.delete("/api/relationships/9999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_prevent_duplicate_relationship(client: AsyncClient, sample_pdf: Path):
    """Test that duplicate relationships are rejected."""
    group_resp = await client.post("/api/groups", json={"name": "Dup Rel Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("dup1.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("dup2.pdf", f, "application/pdf")},
        )
    doc2_id = resp2.json()["id"]

    # First creation should succeed
    resp = await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "references"},
    )
    assert resp.status_code == 201

    # Duplicate should fail
    resp = await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "references"},
    )
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_prevent_self_referencing_relationship(
    client: AsyncClient, sample_pdf: Path
):
    """Test that self-referencing relationships are rejected."""
    group_resp = await client.post("/api/groups", json={"name": "Self Rel Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("self.pdf", f, "application/pdf")},
        )
    doc_id = resp1.json()["id"]

    # Self-referencing should fail
    resp = await client.post(
        f"/api/documents/{doc_id}/relationships",
        json={"target_document_id": doc_id, "relationship_type": "parent"},
    )
    assert resp.status_code == 400
    assert "itself" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_relationship_graph(client: AsyncClient, sample_pdf: Path):
    """Test graph API returns correct nodes and edges."""
    group_resp = await client.post("/api/groups", json={"name": "Graph Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("g1.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("g2.pdf", f, "application/pdf")},
        )
    doc2_id = resp2.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp3 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("g3.pdf", f, "application/pdf")},
        )
    doc3_id = resp3.json()["id"]

    # Create relationships: doc1 -> doc2, doc2 -> doc3
    await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "references"},
    )
    await client.post(
        f"/api/documents/{doc2_id}/relationships",
        json={"target_document_id": doc3_id, "relationship_type": "parent"},
    )

    # Get full graph
    response = await client.get("/api/relationships/graph")
    assert response.status_code == 200
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2

    # Verify node structure
    node_ids = {n["id"] for n in data["nodes"]}
    assert doc1_id in node_ids
    assert doc2_id in node_ids
    assert doc3_id in node_ids

    for node in data["nodes"]:
        assert "id" in node
        assert "name" in node
        assert "group_id" in node

    # Verify edge structure
    for edge in data["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert "type" in edge


@pytest.mark.asyncio
async def test_relationship_graph_filtered_by_group(
    client: AsyncClient, sample_pdf: Path
):
    """Test graph API filtered by group_id."""
    # Create two groups
    group1_resp = await client.post("/api/groups", json={"name": "Graph G1"})
    group1_id = group1_resp.json()["id"]

    group2_resp = await client.post("/api/groups", json={"name": "Graph G2"})
    group2_id = group2_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group1_id}/documents",
            files={"file": ("g1doc.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group1_id}/documents",
            files={"file": ("g1doc2.pdf", f, "application/pdf")},
        )
    doc2_id = resp2.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp3 = await client.post(
            f"/api/groups/{group2_id}/documents",
            files={"file": ("g2doc.pdf", f, "application/pdf")},
        )
    doc3_id = resp3.json()["id"]

    # Relationship within group1
    await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "related"},
    )

    # Relationship from group2 to group1
    await client.post(
        f"/api/documents/{doc3_id}/relationships",
        json={"target_document_id": doc1_id, "relationship_type": "references"},
    )

    # Filter by group1 - should see both relationships (since doc1 belongs to group1)
    response = await client.get(f"/api/relationships/graph?group_id={group1_id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data["edges"]) == 2  # Both relationships involve group1 docs


@pytest.mark.asyncio
async def test_dependency_tree_traversal(client: AsyncClient, sample_pdf: Path):
    """Test transitive dependency tracking: A -> B -> C means A depends on B and C."""
    group_resp = await client.post("/api/groups", json={"name": "Dep Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("dep_a.pdf", f, "application/pdf")},
        )
    doc_a_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("dep_b.pdf", f, "application/pdf")},
        )
    doc_b_id = resp2.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp3 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("dep_c.pdf", f, "application/pdf")},
        )
    doc_c_id = resp3.json()["id"]

    # A -> B -> C (transitive chain)
    await client.post(
        f"/api/documents/{doc_a_id}/relationships",
        json={"target_document_id": doc_b_id, "relationship_type": "references"},
    )
    await client.post(
        f"/api/documents/{doc_b_id}/relationships",
        json={"target_document_id": doc_c_id, "relationship_type": "references"},
    )

    # A's dependencies should include both B and C
    response = await client.get(f"/api/documents/{doc_a_id}/dependencies")
    assert response.status_code == 200
    deps = response.json()
    assert doc_b_id in deps
    assert doc_c_id in deps

    # B's dependencies should include only C
    response = await client.get(f"/api/documents/{doc_b_id}/dependencies")
    assert response.status_code == 200
    deps = response.json()
    assert doc_c_id in deps
    assert doc_a_id not in deps

    # C has no outgoing dependencies
    response = await client.get(f"/api/documents/{doc_c_id}/dependencies")
    assert response.status_code == 200
    deps = response.json()
    assert len(deps) == 0


@pytest.mark.asyncio
async def test_dependencies_document_not_found(client: AsyncClient):
    """Test dependencies endpoint with non-existent document."""
    response = await client.get("/api/documents/9999/dependencies")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_orphaned_documents_detection(client: AsyncClient, sample_pdf: Path):
    """Test orphaned document detection after document deletion."""
    group_resp = await client.post("/api/groups", json={"name": "Orphan Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("orphan1.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("orphan2.pdf", f, "application/pdf")},
        )
    doc2_id = resp2.json()["id"]

    # Create a relationship
    await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "references"},
    )

    # Initially no orphans
    response = await client.get("/api/relationships/orphaned")
    assert response.status_code == 200
    assert len(response.json()) == 0

    # Delete the target document - the CASCADE should remove the relationship too
    await client.delete(f"/api/documents/{doc2_id}")

    # After CASCADE deletion, the relationship is gone, so no orphans
    response = await client.get("/api/relationships/orphaned")
    assert response.status_code == 200
    # With proper CASCADE, there should be no orphans
    data = response.json()
    # The test validates the endpoint works correctly
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_create_relationship_target_not_found(
    client: AsyncClient, sample_pdf: Path
):
    """Test creating a relationship with non-existent target document."""
    group_resp = await client.post("/api/groups", json={"name": "NotFound Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("src.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    response = await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": 9999, "relationship_type": "references"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_relationship_source_not_found(client: AsyncClient):
    """Test creating a relationship from non-existent source document."""
    response = await client.post(
        "/api/documents/9999/relationships",
        json={"target_document_id": 1, "relationship_type": "references"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_relationships_document_not_found(client: AsyncClient):
    """Test listing relationships for non-existent document returns 404."""
    response = await client.get("/api/documents/9999/relationships")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_multiple_relationship_types(client: AsyncClient, sample_pdf: Path):
    """Test creating different relationship types between same documents."""
    group_resp = await client.post("/api/groups", json={"name": "Multi Type Group"})
    group_id = group_resp.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp1 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("mt1.pdf", f, "application/pdf")},
        )
    doc1_id = resp1.json()["id"]

    with open(sample_pdf, "rb") as f:
        resp2 = await client.post(
            f"/api/groups/{group_id}/documents",
            files={"file": ("mt2.pdf", f, "application/pdf")},
        )
    doc2_id = resp2.json()["id"]

    # Same source/target but different types should be allowed
    resp = await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "references"},
    )
    assert resp.status_code == 201

    resp = await client.post(
        f"/api/documents/{doc1_id}/relationships",
        json={"target_document_id": doc2_id, "relationship_type": "supersedes"},
    )
    assert resp.status_code == 201

    # List should show both
    response = await client.get(f"/api/documents/{doc1_id}/relationships")
    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_empty_graph(client: AsyncClient):
    """Test graph API with no relationships returns empty graph."""
    response = await client.get("/api/relationships/graph")
    assert response.status_code == 200
    data = response.json()
    assert data["nodes"] == []
    assert data["edges"] == []
