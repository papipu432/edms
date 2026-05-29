"""Import/Export ecosystem service."""

import csv
import io
import json
import zipfile
from io import BytesIO
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus
from app.models.group import Group


class ImportExportService:
    """Handles import and export of documents and metadata."""

    async def import_zip(self, db: AsyncSession, file: BytesIO) -> dict:
        """Import documents from a ZIP file with manifest.json."""
        documents_created = 0
        groups_created = 0
        errors = []

        try:
            with zipfile.ZipFile(file, "r") as zf:
                # Look for manifest.json
                manifest = None
                if "manifest.json" in zf.namelist():
                    manifest_data = zf.read("manifest.json")
                    manifest = json.loads(manifest_data)

                if manifest:
                    # Process manifest-based import
                    for entry in manifest.get("files", []):
                        try:
                            filename = entry.get("filename", "")
                            folder_path = entry.get("folder_path", "Default")
                            tags = entry.get("tags", [])

                            # Zip-slip protection: reject path traversal in filenames
                            if ".." in filename or filename.startswith("/"):
                                errors.append(f"Rejected unsafe filename: {filename}")
                                continue

                            # Create or find group
                            group = await self._get_or_create_group(db, folder_path)
                            if group:
                                groups_created += 1

                            # Create document record
                            doc = Document(
                                group_id=group.id,
                                original_filename=filename,
                                storage_path=f"/imported/{filename}",
                                file_type=entry.get("file_type", "application/octet-stream"),
                                file_size=entry.get("file_size", 0),
                                status=DocumentStatus.uploaded,
                                keywords=tags if tags else None,
                            )
                            db.add(doc)
                            documents_created += 1
                        except Exception as e:
                            errors.append(f"Error importing {entry.get('filename', 'unknown')}: {str(e)}")
                else:
                    # Directory-structured import
                    for name in zf.namelist():
                        if name.endswith("/"):
                            continue

                        # Zip-slip protection: validate path stays within intended directory
                        resolved = Path(f"/imported/{name}").resolve()
                        if ".." in name.split("/"):
                            continue

                        parts = name.split("/")
                        folder_name = parts[0] if len(parts) > 1 else "Default"
                        filename = parts[-1]

                        group = await self._get_or_create_group(db, folder_name)
                        if group:
                            groups_created += 1

                        doc = Document(
                            group_id=group.id,
                            original_filename=filename,
                            storage_path=f"/imported/{name}",
                            file_type="application/octet-stream",
                            file_size=len(zf.read(name)),
                            status=DocumentStatus.uploaded,
                        )
                        db.add(doc)
                        documents_created += 1

                await db.flush()
        except zipfile.BadZipFile:
            errors.append("Invalid ZIP file")
        except Exception as e:
            errors.append(f"Import error: {str(e)}")

        return {
            "documents_created": documents_created,
            "groups_created": groups_created,
            "errors": errors,
        }

    async def import_csv(
        self, db: AsyncSession, csv_file: BytesIO, zip_file: BytesIO | None = None
    ) -> dict:
        """Import documents using a CSV manifest."""
        documents_created = 0
        groups_created = 0
        errors = []

        try:
            csv_content = csv_file.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(csv_content))

            for row in reader:
                try:
                    filename = row.get("filename", "")
                    folder_path = row.get("folder_path", "Default")
                    tags = row.get("tags", "")
                    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

                    group = await self._get_or_create_group(db, folder_path)
                    if group:
                        groups_created += 1

                    doc = Document(
                        group_id=group.id,
                        original_filename=filename,
                        storage_path=f"/imported/{filename}",
                        file_type="application/octet-stream",
                        file_size=0,
                        status=DocumentStatus.uploaded,
                        keywords=tag_list if tag_list else None,
                    )
                    db.add(doc)
                    documents_created += 1
                except Exception as e:
                    errors.append(f"Error on row: {str(e)}")

            await db.flush()
        except Exception as e:
            errors.append(f"CSV import error: {str(e)}")

        return {
            "documents_created": documents_created,
            "groups_created": groups_created,
            "errors": errors,
        }

    async def export_full(self, db: AsyncSession) -> BytesIO:
        """Export all documents and metadata as a ZIP archive."""
        buffer = BytesIO()
        result = await db.execute(select(Document))
        documents = result.scalars().all()

        metadata = []
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in documents:
                doc_meta = {
                    "id": doc.id,
                    "filename": doc.original_filename,
                    "group_id": doc.group_id,
                    "file_type": doc.file_type,
                    "file_size": doc.file_size,
                    "status": doc.status.value if doc.status else "unknown",
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "storage_path": doc.storage_path,
                }
                metadata.append(doc_meta)

                # Include file content if available
                from pathlib import Path

                storage_path = Path(doc.storage_path)
                if storage_path.exists():
                    zf.write(storage_path, f"documents/{doc.original_filename}")

            zf.writestr("metadata.json", json.dumps(metadata, indent=2))

        buffer.seek(0)
        return buffer

    async def _get_or_create_group(self, db: AsyncSession, name: str) -> Group:
        """Get existing group by name or create a new one."""
        result = await db.execute(select(Group).where(Group.name == name))
        group = result.scalar_one_or_none()
        if group is None:
            group = Group(name=name)
            db.add(group)
            await db.flush()
            await db.refresh(group)
        return group
