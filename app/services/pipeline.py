import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.llm import extract_keywords, generate_embeddings, generate_summary
from app.models.document import Document, DocumentStatus
from app.services.chunker import split_text
from app.services.converter import ConversionService
from app.services.prompt_guard import PromptGuard
from app.services.storage import StorageService
from app.services.vectordb import VectorDBService
from app.services.wiki import WikiService

logger = logging.getLogger(__name__)


class PipelineService:
    """Orchestrates document processing: preprocessing, conversion, and storage."""

    def __init__(self, storage_service: StorageService | None = None) -> None:
        self.conversion = ConversionService()
        self.storage = storage_service or StorageService()
        self._prompt_guard = PromptGuard()

    async def process_document(self, doc_id: int, db: AsyncSession) -> None:
        """Process a document: determine type, convert, and save outputs."""
        document = await db.get(Document, doc_id)
        if not document:
            logger.error("Document %d not found", doc_id)
            return

        # Update status to processing
        document.status = DocumentStatus.processing
        await db.commit()

        try:
            file_path = Path(document.storage_path)
            file_type = document.file_type.lower()

            # Run conversion based on file type
            if "pdf" in file_type or file_path.suffix.lower() == ".pdf":
                result = self.conversion.convert_pdf(file_path)
            elif (
                "wordprocessingml" in file_type
                or "docx" in file_type
                or file_path.suffix.lower() == ".docx"
            ):
                result = self.conversion.convert_docx(file_path)
            elif file_type.startswith("image/") or file_path.suffix.lower() in (
                ".png",
                ".jpg",
                ".jpeg",
                ".tiff",
                ".bmp",
            ):
                result = self.conversion.convert_image(file_path)
            else:
                # Unsupported type - try PDF conversion as fallback
                result = self.conversion.convert_pdf(file_path)

            # If conversion produced an error and no content, consider it failed
            if "error" in result.metadata and not result.markdown_content.strip():
                raise RuntimeError(
                    f"Conversion failed: {result.metadata['error']}"
                )

            # Save markdown output
            group_id = document.group_id

            # Use new data layout if available, with backward compat
            md_content_bytes = result.markdown_content.encode("utf-8")
            markdown_path = self.storage.save_to_data(
                group_id, "md", f"{doc_id}.md", md_content_bytes
            )

            # Save extracted images
            if result.images:
                for idx, img in enumerate(result.images):
                    if hasattr(img, "save"):
                        import io

                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        img_bytes = buf.getvalue()
                    else:
                        # img is a Path
                        img_bytes = Path(img).read_bytes() if not isinstance(img, bytes) else img
                    self.storage.save_to_data(
                        group_id, "images", f"{doc_id}_image_{idx}.png", img_bytes
                    )

            # Save tables as CSV
            if result.tables:
                for idx, csv_content in enumerate(result.tables):
                    csv_bytes = csv_content.encode("utf-8")
                    self.storage.save_to_data(
                        group_id, "csv", f"{doc_id}_table_{idx}.csv", csv_bytes
                    )

            # Move original to data/raw/
            if file_path.exists():
                raw_content = file_path.read_bytes()
                self.storage.save_to_data(
                    group_id, "raw", file_path.name, raw_content
                )

            # Update document in DB
            document.markdown_path = str(markdown_path)

            # Generate summary and keywords using LLM
            markdown_content = result.markdown_content

            # Sanitize content before passing to LLM
            sanitized_content, _ = self._prompt_guard.sanitize(markdown_content)

            summary = generate_summary(sanitized_content)
            keywords = extract_keywords(sanitized_content)
            document.summary = summary
            document.keywords = keywords

            # Chunk content and index in vector DB
            chunks = split_text(markdown_content)
            if chunks:
                embeddings = generate_embeddings(chunks)
                vectordb = VectorDBService()
                vectordb.index_document(
                    doc_id=document.id,
                    group_id=document.group_id,
                    chunks=chunks,
                    embeddings=embeddings,
                )

            # Ingest into wiki
            try:
                wiki = WikiService(wiki_path=settings.WIKI_PATH)
                wiki.ingest(
                    doc_id=document.id,
                    title=document.original_filename,
                    markdown_content=sanitized_content,
                    summary=summary,
                    keywords=keywords,
                    metadata={"group_id": document.group_id},
                )
            except Exception as wiki_err:
                logger.warning(
                    "Wiki ingest failed for document %d: %s", doc_id, wiki_err
                )

            document.status = DocumentStatus.processed
            await db.commit()

            logger.info("Document %d processed successfully", doc_id)

        except Exception as e:
            logger.error("Pipeline failed for document %d: %s", doc_id, e)
            # Refresh to avoid stale state
            await db.rollback()
            result = await db.execute(
                select(Document).where(Document.id == doc_id)
            )
            document = result.scalar_one_or_none()
            if document:
                document.status = DocumentStatus.failed
                await db.commit()
