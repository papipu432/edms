import logging
from pathlib import Path

from Crypto.Random import get_random_bytes
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.version import DocumentVersion

logger = logging.getLogger(__name__)


class VersioningService:
    """Service for managing document versions with independent DEK encryption."""

    def __init__(self, storage_base: str | None = None):
        self._storage_base = storage_base

    @property
    def storage_path(self) -> Path:
        return Path(self._storage_base or settings.STORAGE_PATH)

    async def create_version(
        self,
        db: AsyncSession,
        document_id: int,
        file_content: bytes,
        filename: str,
        file_type: str,
        file_size: int,
        uploader_id: str | None = None,
        changelog: str | None = None,
    ) -> DocumentVersion:
        """Create a new version of a document.

        Stores the file, generates a new DEK, encrypts the version file,
        and stores the wrapped DEK in the version record.
        """
        # Verify document exists
        result = await db.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        # Get next version number
        max_result = await db.execute(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.document_id == document_id
            )
        )
        max_version = max_result.scalar()
        next_version = (max_version or 0) + 1

        # Save file to storage
        storage_base = self.storage_path
        version_dir = storage_base / "versions" / str(document_id)
        version_dir.mkdir(parents=True, exist_ok=True)

        version_filename = f"v{next_version}_{filename}"
        file_path = version_dir / version_filename
        file_path.write_bytes(file_content)

        storage_path = f"versions/{document_id}/{version_filename}"

        # Encrypt version with independent DEK
        wrapped_dek_hex: str | None = None
        encrypted_path: str | None = None

        try:
            from app.services.kms import get_kms_provider

            kms = get_kms_provider()
            dek = get_random_bytes(32)
            wrapped_blob = kms.wrap_key(dek)
            wrapped_dek_hex = wrapped_blob.hex()

            # Encrypt the file
            from app.services.encryption import EnvelopeEncryption

            enc_filename = f"v{next_version}_{filename}.enc"
            enc_path = version_dir / enc_filename
            EnvelopeEncryption.encrypt_file(file_path, enc_path, dek)
            encrypted_path = f"versions/{document_id}/{enc_filename}"

            # Remove plaintext file after successful encryption
            file_path.unlink()
        except (ValueError, OSError, KeyError, NotImplementedError):
            # If KMS/encryption fails due to known issues, store unencrypted
            logger.warning(
                "Encryption failed for version %d of document %d, storing unencrypted",
                next_version,
                document_id,
            )

        # Create version record
        version = DocumentVersion(
            document_id=document_id,
            version_number=next_version,
            storage_path=storage_path,
            encrypted_path=encrypted_path,
            file_size=file_size,
            file_type=file_type,
            uploader_id=uploader_id,
            changelog=changelog,
            wrapped_dek=wrapped_dek_hex,
        )
        db.add(version)

        # Update document's current_version
        document.current_version = next_version
        await db.flush()

        return version

    async def list_versions(
        self,
        db: AsyncSession,
        document_id: int,
    ) -> list[DocumentVersion]:
        """List all versions for a document, ordered by version_number descending."""
        result = await db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_version(
        self,
        db: AsyncSession,
        document_id: int,
        version_id: str,
    ) -> DocumentVersion | None:
        """Get a specific version by ID."""
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
            )
        )
        return result.scalar_one_or_none()

    async def revert_to_version(
        self,
        db: AsyncSession,
        document_id: int,
        version_id: str,
    ) -> Document:
        """Revert a document to a specific version.

        Updates document's current_version, storage_path, and file_size.
        """
        # Get the target version
        result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise ValueError(f"Version {version_id} not found for document {document_id}")

        # Get the document
        doc_result = await db.execute(select(Document).where(Document.id == document_id))
        document = doc_result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        # Update document to point to the target version
        document.current_version = version.version_number
        document.storage_path = version.storage_path
        document.file_size = version.file_size
        if version.encrypted_path:
            document.encrypted_pdf_path = version.encrypted_path

        await db.flush()
        return document

    async def compare_versions(
        self,
        db: AsyncSession,
        document_id: int,
        version_a_num: int,
        version_b_num: int,
    ) -> dict:
        """Compare metadata between two versions."""
        result_a = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_number == version_a_num,
            )
        )
        version_a = result_a.scalar_one_or_none()
        if version_a is None:
            raise ValueError(
                f"Version {version_a_num} not found for document {document_id}"
            )

        result_b = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_number == version_b_num,
            )
        )
        version_b = result_b.scalar_one_or_none()
        if version_b is None:
            raise ValueError(
                f"Version {version_b_num} not found for document {document_id}"
            )

        time_diff = (version_b.created_at - version_a.created_at).total_seconds()

        return {
            "version_a": {
                "version_number": version_a.version_number,
                "file_size": version_a.file_size,
                "file_type": version_a.file_type,
                "uploader_id": version_a.uploader_id,
                "created_at": version_a.created_at,
            },
            "version_b": {
                "version_number": version_b.version_number,
                "file_size": version_b.file_size,
                "file_type": version_b.file_type,
                "uploader_id": version_b.uploader_id,
                "created_at": version_b.created_at,
            },
            "size_diff": version_b.file_size - version_a.file_size,
            "time_diff_seconds": time_diff,
        }
