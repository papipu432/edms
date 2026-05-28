import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.group import Group
from app.models.relationship import DocumentRelationship
from app.schemas.knowledge_graph import KGEdge, KGNode, KnowledgeGraphResponse

logger = logging.getLogger(__name__)


class KnowledgeGraphService:
    async def build_graph(
        self,
        db: AsyncSession,
        document_id: int | None = None,
        group_id: int | None = None,
        entity: str | None = None,
        relationship_type: str | None = None,
    ) -> KnowledgeGraphResponse:
        """Build a knowledge graph from documents, groups, and relationships."""
        nodes: dict[str, KGNode] = {}
        edges: list[KGEdge] = []

        # Query documents with optional filters
        doc_query = select(Document)
        if document_id is not None:
            doc_query = doc_query.where(Document.id == document_id)
        if group_id is not None:
            doc_query = doc_query.where(Document.group_id == group_id)

        result = await db.execute(doc_query)
        documents = result.scalars().all()

        # Build document nodes and collect group IDs
        group_ids: set[int] = set()
        for doc in documents:
            node_id = f"doc_{doc.id}"
            nodes[node_id] = KGNode(
                id=node_id,
                label=doc.original_filename,
                type="document",
                metadata={
                    "file_type": doc.file_type,
                    "status": doc.status.value if doc.status else None,
                    "group_id": doc.group_id,
                },
            )
            group_ids.add(doc.group_id)

            # Extract entity/topic nodes from keywords
            if doc.keywords and isinstance(doc.keywords, list):
                for kw in doc.keywords:
                    if not isinstance(kw, str):
                        continue
                    # Filter by entity if specified
                    if entity and entity.lower() not in kw.lower():
                        continue
                    kw_node_id = f"entity_{kw}"
                    if kw_node_id not in nodes:
                        nodes[kw_node_id] = KGNode(
                            id=kw_node_id,
                            label=kw,
                            type="entity",
                            metadata={},
                        )
                    edges.append(
                        KGEdge(
                            source=node_id,
                            target=kw_node_id,
                            type="has_keyword",
                            label="has keyword",
                        )
                    )

        # Build group nodes
        if group_ids:
            group_query = select(Group).where(Group.id.in_(group_ids))
            group_result = await db.execute(group_query)
            groups = group_result.scalars().all()
            for grp in groups:
                grp_node_id = f"group_{grp.id}"
                nodes[grp_node_id] = KGNode(
                    id=grp_node_id,
                    label=grp.name,
                    type="group",
                    metadata={"description": grp.description},
                )

            # Add document->group edges
            for doc in documents:
                doc_node_id = f"doc_{doc.id}"
                grp_node_id = f"group_{doc.group_id}"
                edges.append(
                    KGEdge(
                        source=doc_node_id,
                        target=grp_node_id,
                        type="belongs_to",
                        label="belongs to",
                    )
                )

        # Query relationships
        rel_query = select(DocumentRelationship)
        if relationship_type is not None:
            rel_query = rel_query.where(
                DocumentRelationship.relationship_type == relationship_type
            )
        # Filter to only relationships involving our documents
        doc_ids = [doc.id for doc in documents]
        if doc_ids:
            rel_query = rel_query.where(
                DocumentRelationship.source_document_id.in_(doc_ids)
                | DocumentRelationship.target_document_id.in_(doc_ids)
            )

        rel_result = await db.execute(rel_query)
        relationships = rel_result.scalars().all()

        for rel in relationships:
            source_id = f"doc_{rel.source_document_id}"
            target_id = f"doc_{rel.target_document_id}"

            # Ensure both nodes exist (target might not be in filtered set)
            if source_id not in nodes:
                # Fetch document info
                src_doc = await db.get(Document, rel.source_document_id)
                if src_doc:
                    nodes[source_id] = KGNode(
                        id=source_id,
                        label=src_doc.original_filename,
                        type="document",
                        metadata={"file_type": src_doc.file_type},
                    )
            if target_id not in nodes:
                tgt_doc = await db.get(Document, rel.target_document_id)
                if tgt_doc:
                    nodes[target_id] = KGNode(
                        id=target_id,
                        label=tgt_doc.original_filename,
                        type="document",
                        metadata={"file_type": tgt_doc.file_type},
                    )

            edges.append(
                KGEdge(
                    source=source_id,
                    target=target_id,
                    type=rel.relationship_type.value if hasattr(rel.relationship_type, "value") else str(rel.relationship_type),
                    label=rel.description or rel.relationship_type.value if hasattr(rel.relationship_type, "value") else str(rel.relationship_type),
                )
            )

        # If entity filter applied and no documents matched keywords, include all entity-matching nodes
        if entity and not documents:
            # Search for documents with matching keywords
            all_docs_result = await db.execute(select(Document))
            all_docs = all_docs_result.scalars().all()
            for doc in all_docs:
                if doc.keywords and isinstance(doc.keywords, list):
                    for kw in doc.keywords:
                        if isinstance(kw, str) and entity.lower() in kw.lower():
                            node_id = f"doc_{doc.id}"
                            if node_id not in nodes:
                                nodes[node_id] = KGNode(
                                    id=node_id,
                                    label=doc.original_filename,
                                    type="document",
                                    metadata={"file_type": doc.file_type},
                                )
                            kw_node_id = f"entity_{kw}"
                            if kw_node_id not in nodes:
                                nodes[kw_node_id] = KGNode(
                                    id=kw_node_id,
                                    label=kw,
                                    type="entity",
                                    metadata={},
                                )
                            edges.append(
                                KGEdge(
                                    source=node_id,
                                    target=kw_node_id,
                                    type="has_keyword",
                                    label="has keyword",
                                )
                            )

        return KnowledgeGraphResponse(
            nodes=list(nodes.values()),
            edges=edges,
        )
