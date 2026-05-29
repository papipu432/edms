from datetime import datetime

from pydantic import BaseModel

from app.models.relationship import RelationshipType


class RelationshipCreate(BaseModel):
    target_document_id: int
    relationship_type: RelationshipType
    description: str | None = None


class RelationshipResponse(BaseModel):
    id: int
    source_document_id: int
    target_document_id: int
    relationship_type: RelationshipType
    description: str | None = None
    created_by: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class GraphNode(BaseModel):
    id: int
    name: str
    group_id: int


class GraphEdge(BaseModel):
    source: int
    target: int
    type: RelationshipType


class RelationshipGraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class OrphanedDocumentResponse(BaseModel):
    document_id: int
    document_name: str
    issue: str
