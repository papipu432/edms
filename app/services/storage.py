import os
import shutil
from pathlib import Path

import pikepdf
from fastapi import UploadFile

from app.core.config import settings


class StorageService:
    def __init__(self, base_path: str | None = None):
        self.base_path = Path(base_path or settings.STORAGE_PATH)

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
