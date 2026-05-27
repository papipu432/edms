import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.services.converter import ConversionService
from app.services.storage import StorageService

logger = logging.getLogger(__name__)


class PipelineService:
    """Orchestrates document processing: preprocessing, conversion, and storage."""

    def __init__(self, storage_service: StorageService | None = None) -> None:
        self.conversion = ConversionService()
        self.storage = storage_service or StorageService()

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
            base_path = self.storage.base_path
            markdown_dir = base_path / str(group_id) / "markdown"
            markdown_dir.mkdir(parents=True, exist_ok=True)
            markdown_path = markdown_dir / f"{doc_id}.md"
            markdown_path.write_text(result.markdown_content, encoding="utf-8")

            # Save extracted images
            if result.images:
                images_dir = base_path / str(group_id) / "images" / str(doc_id)
                images_dir.mkdir(parents=True, exist_ok=True)
                for idx, img in enumerate(result.images):
                    img_path = images_dir / f"image_{idx}.png"
                    if hasattr(img, "save"):
                        img.save(str(img_path))
                    # If img is already a Path, it's already saved

            # Save tables as CSV
            if result.tables:
                tables_dir = base_path / str(group_id) / "tables" / str(doc_id)
                tables_dir.mkdir(parents=True, exist_ok=True)
                for idx, csv_content in enumerate(result.tables):
                    table_path = tables_dir / f"table_{idx}.csv"
                    table_path.write_text(csv_content, encoding="utf-8")

            # Update document in DB
            document.markdown_path = str(markdown_path)
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
