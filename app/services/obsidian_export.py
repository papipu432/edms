"""Service for exporting the wiki as an Obsidian-compatible vault."""

import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


class ObsidianExportService:
    """Converts wiki pages to Obsidian-compatible format with wikilinks and frontmatter."""

    def __init__(self, wiki_path: str) -> None:
        self.wiki_path = Path(wiki_path)

    def convert_to_wikilinks(self, content: str) -> str:
        """Convert markdown links like [text](../entities/foo.md) to [[foo]] wikilinks.

        Handles relative links within the wiki structure. External links (http/https)
        are left unchanged.
        """
        def replace_link(match: re.Match) -> str:
            target = match.group(2)

            # Skip external links
            if target.startswith("http://") or target.startswith("https://"):
                return match.group(0)

            # Extract the slug from the path (filename without .md)
            # Handle paths like ../entities/foo.md, ../summaries/1.md, etc.
            path = Path(target)
            slug = path.stem  # filename without extension

            return f"[[{slug}]]"

        # Match markdown links [text](path)
        link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
        return link_pattern.sub(replace_link, content)

    def _detect_page_type(self, page_path: str) -> str:
        """Detect page type from its path (entity, topic, or summary)."""
        if page_path.startswith("entities/"):
            return "entity"
        elif page_path.startswith("topics/"):
            return "topic"
        elif page_path.startswith("summaries/"):
            return "summary"
        return "unknown"

    def _extract_title(self, content: str) -> str:
        """Extract title from the first H1 heading."""
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return ""

    def _extract_document_ids(self, content: str) -> list[str]:
        """Extract document IDs from content (from 'Document {id}' pattern)."""
        matches = re.findall(r"Document\s+(\d+)", content)
        return sorted(set(matches))

    def _extract_keywords(self, content: str) -> list[str]:
        """Extract keywords from summary pages (from 'Keywords:' line)."""
        match = re.search(r"\*\*Keywords:\*\*\s*(.+)$", content, re.MULTILINE)
        if match:
            keywords_str = match.group(1).strip()
            return [k.strip() for k in keywords_str.split(",") if k.strip()]
        return []

    def _extract_related_entities(self, content: str) -> list[str]:
        """Extract related entity links from content."""
        # Match links to entities like [text](../entities/foo.md)
        matches = re.findall(r"\[([^\]]*)\]\(\.\./entities/([^)]+)\.md\)", content)
        return [slug for _, slug in matches]

    def generate_frontmatter(self, page_path: str, content: str) -> str:
        """Generate YAML frontmatter with metadata and Dataview-compatible properties."""
        page_type = self._detect_page_type(page_path)
        title = self._extract_title(content)
        doc_ids = self._extract_document_ids(content)
        slug = Path(page_path).stem

        # Build frontmatter fields
        lines = ["---"]
        lines.append(f"title: \"{title}\"")
        lines.append(f"type:: {page_type}")

        # Tags based on page type and content
        tags: list[str] = [page_type]
        if page_type == "summary":
            keywords = self._extract_keywords(content)
            tags.extend(keywords)
        lines.append(f"tags: [{', '.join(tags)}]")

        # Aliases
        aliases: list[str] = [slug]
        if title and title != slug:
            aliases.append(title)
        lines.append(f"aliases: [{', '.join(aliases)}]")

        # Dates - use file modification time if available, otherwise current time
        full_path = self.wiki_path / page_path
        if full_path.exists():
            mtime = full_path.stat().st_mtime
            date_modified = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            # Use mtime as created date too (we don't track creation time separately)
            date_created = date_modified
        else:
            now = datetime.now(timezone.utc).isoformat()
            date_created = now
            date_modified = now

        lines.append(f"date_created:: {date_created}")
        lines.append(f"date_modified:: {date_modified}")

        # Source documents
        if doc_ids:
            doc_list = ", ".join(doc_ids)
            lines.append(f"source_documents:: [{doc_list}]")
        else:
            lines.append("source_documents:: []")

        # Related entities (for entity and topic pages)
        if page_type in ("entity", "topic"):
            related = self._extract_related_entities(content)
            if related:
                related_list = ", ".join(related)
                lines.append(f"related:: [{related_list}]")

        lines.append("---")
        return "\n".join(lines)

    def export_page(self, page_path: str, content: str) -> str:
        """Export a single page in Obsidian format (frontmatter + converted content)."""
        frontmatter = self.generate_frontmatter(page_path, content)
        converted_content = self.convert_to_wikilinks(content)
        return f"{frontmatter}\n{converted_content}"

    def export_vault(self, wiki_path: str | None = None) -> dict[str, str]:
        """Generate full vault as dict {filename: content}.

        Args:
            wiki_path: Optional override for wiki path. Uses self.wiki_path if None.

        Returns:
            Dictionary mapping relative file paths to their Obsidian-formatted content.
        """
        path = Path(wiki_path) if wiki_path else self.wiki_path
        vault: dict[str, str] = {}

        for subdir in ["entities", "topics", "summaries"]:
            dir_path = path / subdir
            if not dir_path.exists():
                continue
            for page_file in sorted(dir_path.iterdir()):
                if page_file.suffix == ".md":
                    page_path = f"{subdir}/{page_file.name}"
                    content = page_file.read_text(encoding="utf-8")
                    vault[page_path] = self.export_page(page_path, content)

        return vault

    def create_vault_zip(self, wiki_path: str | None = None) -> io.BytesIO:
        """Create a zip file in-memory containing the full Obsidian vault.

        Args:
            wiki_path: Optional override for wiki path. Uses self.wiki_path if None.

        Returns:
            BytesIO object containing the zip file data.
        """
        vault = self.export_vault(wiki_path)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in sorted(vault.items()):
                zf.writestr(filename, content)

        zip_buffer.seek(0)
        return zip_buffer

    def get_sync_changes(
        self, wiki_path: str | None = None, since_timestamp: str | None = None
    ) -> dict[str, list[str]]:
        """Return pages modified after the given timestamp.

        Args:
            wiki_path: Optional override for wiki path. Uses self.wiki_path if None.
            since_timestamp: ISO 8601 timestamp. Pages modified after this time are returned.

        Returns:
            Dict with 'changed' (list of modified page paths) and 'deleted' (empty list).
        """
        path = Path(wiki_path) if wiki_path else self.wiki_path
        changed: list[str] = []

        if since_timestamp:
            since_dt = datetime.fromisoformat(since_timestamp)
            # Ensure timezone-aware comparison
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        else:
            # If no timestamp provided, return all pages
            since_dt = datetime.min.replace(tzinfo=timezone.utc)

        for subdir in ["entities", "topics", "summaries"]:
            dir_path = path / subdir
            if not dir_path.exists():
                continue
            for page_file in sorted(dir_path.iterdir()):
                if page_file.suffix == ".md":
                    mtime = page_file.stat().st_mtime
                    file_dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
                    if file_dt > since_dt:
                        changed.append(f"{subdir}/{page_file.name}")

        return {"changed": changed, "deleted": []}
