from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.relationship import DocumentRelationship, RelationshipType


class RelationshipService:
    """Service for managing document relationships and cross-reference graphs."""

    async def add_relationship(
        self,
        db: AsyncSession,
        source_document_id: int,
        target_document_id: int,
        relationship_type: RelationshipType,
        description: str | None = None,
        created_by: int | None = None,
    ) -> DocumentRelationship:
        """Create a new relationship between two documents."""
        # Prevent self-referencing
        if source_document_id == target_document_id:
            raise ValueError("A document cannot have a relationship with itself")

        # Verify both documents exist
        source = await db.get(Document, source_document_id)
        if not source:
            raise ValueError(f"Source document {source_document_id} not found")

        target = await db.get(Document, target_document_id)
        if not target:
            raise ValueError(f"Target document {target_document_id} not found")

        # Check for duplicate
        existing = await db.execute(
            select(DocumentRelationship).where(
                and_(
                    DocumentRelationship.source_document_id == source_document_id,
                    DocumentRelationship.target_document_id == target_document_id,
                    DocumentRelationship.relationship_type == relationship_type,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                "A relationship with the same source, target, and type already exists"
            )

        relationship = DocumentRelationship(
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            relationship_type=relationship_type,
            description=description,
            created_by=created_by,
        )
        db.add(relationship)
        await db.flush()
        await db.refresh(relationship)
        return relationship

    async def remove_relationship(
        self,
        db: AsyncSession,
        relationship_id: int,
    ) -> bool:
        """Remove a relationship by ID. Returns True if deleted, False if not found."""
        rel = await db.get(DocumentRelationship, relationship_id)
        if not rel:
            return False
        await db.delete(rel)
        return True

    async def get_document_relationships(
        self,
        db: AsyncSession,
        document_id: int,
    ) -> list[DocumentRelationship]:
        """Get all relationships where the document is source or target."""
        result = await db.execute(
            select(DocumentRelationship).where(
                (DocumentRelationship.source_document_id == document_id)
                | (DocumentRelationship.target_document_id == document_id)
            )
        )
        return list(result.scalars().all())

    async def get_relationship_graph(
        self,
        db: AsyncSession,
        group_id: int | None = None,
    ) -> dict:
        """Build a graph representation of document relationships.

        Returns nodes (documents) and edges (relationships).
        Optionally filtered by group_id.
        """
        # Get relationships
        query = select(DocumentRelationship)
        if group_id is not None:
            # Filter by relationships where source or target belongs to the group
            source_docs = select(Document.id).where(Document.group_id == group_id)
            query = query.where(
                (DocumentRelationship.source_document_id.in_(source_docs))
                | (DocumentRelationship.target_document_id.in_(source_docs))
            )

        result = await db.execute(query)
        relationships = list(result.scalars().all())

        # Collect all document IDs involved
        doc_ids: set[int] = set()
        edges = []
        for rel in relationships:
            doc_ids.add(rel.source_document_id)
            doc_ids.add(rel.target_document_id)
            edges.append(
                {
                    "source": rel.source_document_id,
                    "target": rel.target_document_id,
                    "type": rel.relationship_type,
                }
            )

        # Get document info for nodes
        nodes = []
        if doc_ids:
            docs_result = await db.execute(
                select(Document).where(Document.id.in_(doc_ids))
            )
            for doc in docs_result.scalars().all():
                nodes.append(
                    {
                        "id": doc.id,
                        "name": doc.original_filename,
                        "group_id": doc.group_id,
                    }
                )

        return {"nodes": nodes, "edges": edges}

    async def detect_orphaned_documents(
        self,
        db: AsyncSession,
    ) -> list[dict]:
        """Detect documents that have relationships pointing to non-existent targets.

        An orphaned relationship is one where the target document has been deleted
        but the relationship record still exists (should not happen with CASCADE,
        but this also finds documents with no relationships at all that might be
        isolated in the system).
        """
        # Find relationships where target document no longer exists
        # With CASCADE this should be rare, but we also find documents
        # that have relationships with missing targets
        all_docs_result = await db.execute(select(Document))
        all_docs = {doc.id: doc for doc in all_docs_result.scalars().all()}

        all_rels_result = await db.execute(select(DocumentRelationship))
        all_rels = list(all_rels_result.scalars().all())

        orphaned = []
        seen_docs: set[int] = set()

        for rel in all_rels:
            # Check if source doc exists but target doesn't
            if rel.source_document_id in all_docs and rel.target_document_id not in all_docs:
                if rel.source_document_id not in seen_docs:
                    seen_docs.add(rel.source_document_id)
                    doc = all_docs[rel.source_document_id]
                    orphaned.append(
                        {
                            "document_id": doc.id,
                            "document_name": doc.original_filename,
                            "issue": f"References non-existent document {rel.target_document_id}",
                        }
                    )
            # Check if target doc exists but source doesn't
            if rel.target_document_id in all_docs and rel.source_document_id not in all_docs:
                if rel.target_document_id not in seen_docs:
                    seen_docs.add(rel.target_document_id)
                    doc = all_docs[rel.target_document_id]
                    orphaned.append(
                        {
                            "document_id": doc.id,
                            "document_name": doc.original_filename,
                            "issue": f"Referenced by non-existent document {rel.source_document_id}",
                        }
                    )

        return orphaned

    async def get_document_dependencies(
        self,
        db: AsyncSession,
        document_id: int,
    ) -> list[int]:
        """Get transitive dependencies for a document.

        Traverses the relationship graph following outgoing relationships
        (where the document is the source) transitively.
        If A -> B and B -> C, then A's dependencies are [B, C].
        """
        visited: set[int] = set()
        queue: list[int] = [document_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            # Find all outgoing relationships from current
            result = await db.execute(
                select(DocumentRelationship.target_document_id).where(
                    DocumentRelationship.source_document_id == current
                )
            )
            targets = [row[0] for row in result.all()]
            for target in targets:
                if target not in visited:
                    queue.append(target)

        # Remove the starting document from results
        visited.discard(document_id)
        return sorted(visited)
