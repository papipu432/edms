"""Service for bi-directional Obsidian sync import."""

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from app.schemas.obsidian_sync import SyncConflict, SyncManifest, SyncResult


class ObsidianSyncService:
    """Handles importing an Obsidian vault zip into the wiki."""

    def __init__(self, wiki_path: str) -> None:
        self.wiki_path = Path(wiki_path)
        self.manifest_path = self.wiki_path / "sync_manifest.json"

    def _compute_hash(self, content: bytes) -> str:
        """Compute SHA256 hash of file content."""
        return hashlib.sha256(content).hexdigest()

    def _load_manifest(self) -> SyncManifest:
        """Load the sync manifest or return a fresh one."""
        if self.manifest_path.exists():
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return SyncManifest(**data)
        return SyncManifest(last_sync="", file_hashes={})

    def _save_manifest(self, manifest: SyncManifest) -> None:
        """Persist the sync manifest to disk."""
        self.manifest_path.write_text(
            json.dumps(manifest.model_dump(), indent=2),
            encoding="utf-8",
        )

    def _get_wiki_files(self) -> dict[str, bytes]:
        """Read all .md files from the wiki directory."""
        files: dict[str, bytes] = {}
        for subdir in ["entities", "topics", "summaries"]:
            dir_path = self.wiki_path / subdir
            if dir_path.exists():
                for f in dir_path.iterdir():
                    if f.suffix == ".md":
                        rel = f"{subdir}/{f.name}"
                        files[rel] = f.read_bytes()
        return files

    def _is_edms_protected(self, path: str) -> bool:
        """Check if a path is EDMS-protected (summaries directory)."""
        return path.startswith("summaries/")

    def import_zip(self, zip_data: bytes) -> SyncResult:
        """Import a zip of markdown files into the wiki.

        Conflict resolution:
        - Obsidian wins for user-created pages (entities/, topics/)
        - EDMS wins for auto-generated summaries (summaries/)
        """
        self.wiki_path.mkdir(parents=True, exist_ok=True)
        for subdir in ["entities", "topics", "summaries"]:
            (self.wiki_path / subdir).mkdir(exist_ok=True)

        manifest = self._load_manifest()

        # Extract zip contents
        zip_files: dict[str, bytes] = {}
        with zipfile.ZipFile(BytesIO(zip_data), "r") as zf:
            for name in zf.namelist():
                if name.endswith(".md") and not name.startswith("__"):
                    content = zf.read(name)
                    zip_files[name] = content

        # Get current wiki files
        wiki_files = self._get_wiki_files()

        pages_created = 0
        pages_updated = 0
        pages_deleted = 0
        conflicts: list[SyncConflict] = []
        new_hashes: dict[str, str] = {}

        # Process files in zip
        for path, content in zip_files.items():
            # Validate path stays within wiki directory (zip-slip protection)
            resolved = (self.wiki_path / path).resolve()
            if not resolved.is_relative_to(self.wiki_path.resolve()):
                continue

            file_hash = self._compute_hash(content)
            new_hashes[path] = file_hash

            if path not in wiki_files:
                # New page - create it
                full_path = self.wiki_path / path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_bytes(content)
                pages_created += 1
            else:
                # Existing page - check if modified
                existing_hash = self._compute_hash(wiki_files[path])
                if file_hash != existing_hash:
                    if self._is_edms_protected(path):
                        # EDMS wins for summaries
                        conflicts.append(
                            SyncConflict(
                                path=path,
                                resolution="edms_wins",
                                detail="Auto-generated summary kept; Obsidian version ignored",
                            )
                        )
                        new_hashes[path] = existing_hash
                    else:
                        # Obsidian wins for entities/topics
                        full_path = self.wiki_path / path
                        full_path.write_bytes(content)
                        pages_updated += 1

        # Detect deleted pages (in wiki but not in zip)
        for path in wiki_files:
            if path not in zip_files:
                if not self._is_edms_protected(path):
                    full_path = self.wiki_path / path
                    if full_path.exists():
                        full_path.unlink()
                        pages_deleted += 1
                else:
                    # Keep EDMS-protected files even if not in zip
                    new_hashes[path] = self._compute_hash(wiki_files[path])

        # Also keep hashes for remaining protected files
        for path in wiki_files:
            if path not in new_hashes and self._is_edms_protected(path):
                new_hashes[path] = self._compute_hash(wiki_files[path])

        # Update manifest
        manifest.last_sync = datetime.now(timezone.utc).isoformat()
        manifest.file_hashes = new_hashes
        self._save_manifest(manifest)

        return SyncResult(
            pages_created=pages_created,
            pages_updated=pages_updated,
            pages_deleted=pages_deleted,
            conflicts=conflicts,
        )
