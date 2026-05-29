from pydantic import BaseModel


class KGNode(BaseModel):
    id: str
    label: str
    type: str  # document, entity, topic, group
    metadata: dict = {}


class KGEdge(BaseModel):
    source: str
    target: str
    type: str
    label: str


class KnowledgeGraphResponse(BaseModel):
    nodes: list[KGNode]
    edges: list[KGEdge]
