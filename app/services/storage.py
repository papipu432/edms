import os
import shutil
import tempfile
from pathlib import Path

import pikepdf
from fastapi import UploadFile

from app.core.config import settings


class StorageService:
    """Manages file storage with optional envelope encryption.

    Directory layout per group:
        <group_id>/
            uploads/          - temporary unencrypted waiting area
            data/
                raw/          - original files (optionally encrypted)
                md/           - converted markdown (optionally encrypted)
                csv/          - extracted tables (optionally encrypted)
                images/       - extracted images (optionally encrypted)
                vectors/      - vector embeddings (not encrypted)
            originals/        - legacy directory (backward compat)
            encrypted/        - legacy directory (backward compat)
            markdown/         - legacy directory (backward compat)
            images/           - legacy directory (backward compat)
    """

    DATA_CATEGORIES = ("raw", "md", "csv", "images", "vectors")

    def __init__(self, base_path: str | None = None, kek: bytes | None = None):
        self.base_path = Path(base_path or settings.STORAGE_PATH)
        self.kek = kek

    def _ensure_dirs(self, group_id: int) -> dict[str, Path]:
        dirs = {
            "originals": self.base_path / str(group_id) / "originals",
            "encrypted": self.base_path / str(group_id) / "encrypted",
            "markdown": self.base_path / str(group_id) / "markdown",
            "images": self.base_path / str(group_id) / "images",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs

    def _ensure_data_dirs(self, group_id: int) -> dict[str, Path]:
        """Ensure new data layout directories exist."""
        base = self.base_path / str(group_id)
        dirs = {
            "uploads": base / "uploads",
            "raw": base / "data" / "raw",
            "md": base / "data" / "md",
            "csv": base / "data" / "csv",
            "images": base / "data" / "images",
            "vectors": base / "data" / "vectors",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs

    async def save_upload(
        self, group_id: int, file: UploadFile, filename: str
    ) -> Path:
        dirs = self._ensure_dirs(group_id)
        file_path = dirs["originals"] / filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        return file_path

    def encrypt_pdf(self, group_id: int, source_path: Path, filename: str) -> Path:
        dirs = self._ensure_dirs(group_id)
        encrypted_path = dirs["encrypted"] / filename
        password = settings.PDF_ENCRYPTION_PASSWORD

        with pikepdf.open(source_path) as pdf:
            pdf.save(
                encrypted_path,
                encryption=pikepdf.Encryption(
                    owner=password, user=password, R=6
                ),
            )
        return encrypted_path

    def get_file_path(self, relative_path: str) -> Path:
        return self.base_path / relative_path

    def delete_file(self, relative_path: str) -> None:
        file_path = self.base_path / relative_path
        if file_path.is_file():
            os.remove(file_path)
        elif file_path.is_dir():
            shutil.rmtree(file_path)

    def save_to_data(
        self,
        group_id: int,
        category: str,
        filename: str,
        content: bytes,
        kek: bytes | None = None,
    ) -> Path:
        """Save content to a data category directory, optionally encrypting.

        Args:
            group_id: The group (tenant) identifier.
            category: One of 'raw', 'md', 'csv', 'images', 'vectors'.
            filename: Target filename.
            content: File content as bytes.
            kek: Key Encryption Key. If provided, file is encrypted.
                 If None, falls back to self.kek. If both None, stored unencrypted.

        Returns:
            Path to the stored file.
        """
        if category not in self.DATA_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

        dirs = self._ensure_data_dirs(group_id)
        target_path = dirs[category] / filename

        effective_kek = kek if kek is not None else self.kek

        if effective_kek is not None and category != "vectors":
            # Encrypt the file using envelope encryption
            from app.services.encryption import EnvelopeEncryption

            # Write content to a temp file, then encrypt to target
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            try:
                EnvelopeEncryption.encrypt_file(tmp_path, target_path, effective_kek)
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            # Store unencrypted
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(content)

        return target_path

    def read_from_data(
        self,
        group_id: int,
        category: str,
        filename: str,
        kek: bytes | None = None,
    ) -> bytes:
        """Read content from a data category directory, optionally decrypting.

        Args:
            group_id: The group (tenant) identifier.
            category: One of 'raw', 'md', 'csv', 'images', 'vectors'.
            filename: Target filename.
            kek: Key Encryption Key. If provided, file is decrypted.
                 If None, falls back to self.kek. If both None, read raw bytes.

        Returns:
            File content as bytes.
        """
        if category not in self.DATA_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")

        base = self.base_path / str(group_id)
        file_path = base / "data" / category / filename

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        effective_kek = kek if kek is not None else self.kek

        if effective_kek is not None and category != "vectors":
            # Decrypt the file
            from app.services.encryption import EnvelopeEncryption

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                EnvelopeEncryption.decrypt_file(file_path, tmp_path, effective_kek)
                return tmp_path.read_bytes()
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            return file_path.read_bytes()

    def save_to_uploads(
        self, group_id: int, filename: str, content: bytes
    ) -> Path:
        """Save a file to the uploads/ directory (never encrypted)."""
        dirs = self._ensure_data_dirs(group_id)
        target_path = dirs["uploads"] / filename
        target_path.write_bytes(content)
        return target_path
