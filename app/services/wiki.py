import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from app.core.llm import chat_completion, get_llm_client

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


class WikiService:
    """Manages an LLM-powered wiki of interlinked markdown files."""

    def __init__(self, wiki_path: str) -> None:
        self.wiki_path = Path(wiki_path)
        self._ensure_structure()

    def _ensure_structure(self) -> None:
        """Create the wiki directory structure if it doesn't exist."""
        self.wiki_path.mkdir(parents=True, exist_ok=True)
        (self.wiki_path / "entities").mkdir(exist_ok=True)
        (self.wiki_path / "topics").mkdir(exist_ok=True)
        (self.wiki_path / "summaries").mkdir(exist_ok=True)

        index_path = self.wiki_path / "index.md"
        if not index_path.exists():
            index_path.write_text(
                "# Wiki Index\n\nThis is the wiki index.\n\n## Documents\n\n## Entities\n\n## Topics\n",
                encoding="utf-8",
            )

        log_path = self.wiki_path / "log.md"
        if not log_path.exists():
            log_path.write_text(
                "# Wiki Operation Log\n\n", encoding="utf-8"
            )

    def _extract_entities_and_topics(self, content: str) -> dict:
        """Use LLM to extract entities and topics from content."""
        client = get_llm_client()
        if client is None:
            return {"entities": [], "topics": []}

        prompt = (
            "Extract key entities (people, organizations, technologies, places) "
            "and topics (concepts, themes, subjects) from the following text. "
            "Return a JSON object with two keys: 'entities' (list of strings) "
            "and 'topics' (list of strings). Return ONLY the JSON, no other text.\n\n"
            f"Text:\n{content[:4000]}"
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract structured information from text. Always return valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
            )
            result_text = response.choices[0].message.content or "{}"
            # Try to parse JSON from the response
            result_text = result_text.strip()
            if result_text.startswith("```"):
                # Strip code fences
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1])
            return json.loads(result_text)
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Failed to extract entities/topics: %s", e)
            return {"entities": [], "topics": []}

    def _merge_page_content(self, existing_content: str, new_info: str) -> str:
        """Use LLM to merge new information into an existing wiki page."""
        client = get_llm_client()
        if client is None:
            return existing_content + "\n\n" + new_info

        prompt = (
            "You are updating a wiki page. Merge the new information into the existing page content. "
            "Keep the page well-organized and avoid duplicating information. "
            "Return ONLY the updated markdown content.\n\n"
            f"Existing page:\n{existing_content}\n\n"
            f"New information to integrate:\n{new_info}"
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a wiki editor that merges information cleanly."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1000,
            )
            return response.choices[0].message.content or existing_content
        except Exception as e:
            logger.error("Failed to merge page content: %s", e)
            return existing_content + "\n\n" + new_info

    def ingest(
        self,
        doc_id: int,
        title: str,
        markdown_content: str,
        summary: str,
        keywords: list[str],
        metadata: dict,
    ) -> None:
        """Ingest a document into the wiki."""
        timestamp = datetime.now(timezone.utc).isoformat()

        # (a) Create summary page
        summary_path = self.wiki_path / "summaries" / f"{doc_id}.md"
        summary_content = (
            f"# {title}\n\n"
            f"**Document ID:** {doc_id}\n\n"
            f"**Date:** {timestamp}\n\n"
            f"**Keywords:** {', '.join(keywords)}\n\n"
            f"## Summary\n\n{summary}\n"
        )
        summary_path.write_text(summary_content, encoding="utf-8")

        # (b) Extract entities and topics from content
        extracted = self._extract_entities_and_topics(markdown_content)
        entities = extracted.get("entities", [])
        topics = extracted.get("topics", [])

        # (c) Create/update entity pages
        entity_slugs = []
        for entity in entities:
            slug = _slugify(entity)
            if not slug:
                continue
            entity_slugs.append(slug)
            entity_path = self.wiki_path / "entities" / f"{slug}.md"
            new_info = f"Referenced in [{title}](../summaries/{doc_id}.md) (Document {doc_id})."

            if entity_path.exists():
                existing = entity_path.read_text(encoding="utf-8")
                merged = self._merge_page_content(existing, new_info)
                entity_path.write_text(merged, encoding="utf-8")
            else:
                page_content = (
                    f"# {entity}\n\n"
                    f"{new_info}\n"
                )
                entity_path.write_text(page_content, encoding="utf-8")

        # (d) Create/update topic pages
        topic_slugs = []
        for topic in topics:
            slug = _slugify(topic)
            if not slug:
                continue
            topic_slugs.append(slug)
            topic_path = self.wiki_path / "topics" / f"{slug}.md"
            new_info = f"Referenced in [{title}](../summaries/{doc_id}.md) (Document {doc_id})."

            if topic_path.exists():
                existing = topic_path.read_text(encoding="utf-8")
                merged = self._merge_page_content(existing, new_info)
                topic_path.write_text(merged, encoding="utf-8")
            else:
                page_content = (
                    f"# {topic}\n\n"
                    f"{new_info}\n"
                )
                topic_path.write_text(page_content, encoding="utf-8")

        # (e) Update index.md
        self._update_index(doc_id, title, entity_slugs, topic_slugs)

        # (f) Append to log.md
        entities_str = ", ".join(entity_slugs) if entity_slugs else "none"
        topics_str = ", ".join(topic_slugs) if topic_slugs else "none"
        log_entry = (
            f"- [{timestamp}] **ingest** | doc_id={doc_id} | "
            f"title=\"{title}\" | entities: {entities_str} | topics: {topics_str}\n"
        )
        log_path = self.wiki_path / "log.md"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

    def _update_index(
        self, doc_id: int, title: str, entity_slugs: list[str], topic_slugs: list[str]
    ) -> None:
        """Update index.md with new document entry and entity/topic pages."""
        index_path = self.wiki_path / "index.md"
        content = index_path.read_text(encoding="utf-8")

        # Add document entry if not present
        doc_entry = f"- [{title}](summaries/{doc_id}.md)"
        if doc_entry not in content:
            content = content.replace(
                "## Documents\n",
                f"## Documents\n\n{doc_entry}\n",
            )

        # Add entity entries
        for slug in entity_slugs:
            entity_entry = f"- [{slug}](entities/{slug}.md)"
            if entity_entry not in content:
                content = content.replace(
                    "## Entities\n",
                    f"## Entities\n\n{entity_entry}\n",
                )

        # Add topic entries
        for slug in topic_slugs:
            topic_entry = f"- [{slug}](topics/{slug}.md)"
            if topic_entry not in content:
                content = content.replace(
                    "## Topics\n",
                    f"## Topics\n\n{topic_entry}\n",
                )

        index_path.write_text(content, encoding="utf-8")

    def query(self, question: str) -> str:
        """Search the wiki and answer a question using LLM."""
        # Read index to find relevant pages
        index_path = self.wiki_path / "index.md"
        index_content = index_path.read_text(encoding="utf-8")

        # Gather content from wiki pages
        context_parts = [f"Wiki Index:\n{index_content}"]

        # Read entity pages
        entities_dir = self.wiki_path / "entities"
        if entities_dir.exists():
            for page_file in entities_dir.iterdir():
                if page_file.suffix == ".md":
                    context_parts.append(
                        f"\n--- entities/{page_file.name} ---\n"
                        + page_file.read_text(encoding="utf-8")
                    )

        # Read topic pages
        topics_dir = self.wiki_path / "topics"
        if topics_dir.exists():
            for page_file in topics_dir.iterdir():
                if page_file.suffix == ".md":
                    context_parts.append(
                        f"\n--- topics/{page_file.name} ---\n"
                        + page_file.read_text(encoding="utf-8")
                    )

        # Read summary pages
        summaries_dir = self.wiki_path / "summaries"
        if summaries_dir.exists():
            for page_file in summaries_dir.iterdir():
                if page_file.suffix == ".md":
                    context_parts.append(
                        f"\n--- summaries/{page_file.name} ---\n"
                        + page_file.read_text(encoding="utf-8")
                    )

        wiki_context = "\n".join(context_parts)

        # Use chat_completion to answer
        messages = [{"role": "user", "content": question}]
        answer = chat_completion(messages, context=wiki_context)
        return answer

    def lint(self) -> list[dict]:
        """Check wiki health and return issues found."""
        issues: list[dict] = []

        # Read index.md to get listed pages
        index_path = self.wiki_path / "index.md"
        index_content = index_path.read_text(encoding="utf-8")

        # Extract all markdown links from index
        link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
        indexed_paths: set[str] = set()
        for _text, path in link_pattern.findall(index_content):
            indexed_paths.add(path)

        # Check for orphan pages in entities/
        entities_dir = self.wiki_path / "entities"
        if entities_dir.exists():
            for page_file in entities_dir.iterdir():
                if page_file.suffix == ".md":
                    relative_path = f"entities/{page_file.name}"
                    if relative_path not in indexed_paths:
                        issues.append({
                            "type": "orphan_page",
                            "detail": f"Page '{relative_path}' not listed in index.md",
                            "file": relative_path,
                        })

        # Check for orphan pages in topics/
        topics_dir = self.wiki_path / "topics"
        if topics_dir.exists():
            for page_file in topics_dir.iterdir():
                if page_file.suffix == ".md":
                    relative_path = f"topics/{page_file.name}"
                    if relative_path not in indexed_paths:
                        issues.append({
                            "type": "orphan_page",
                            "detail": f"Page '{relative_path}' not listed in index.md",
                            "file": relative_path,
                        })

        # Check for broken links in all wiki files
        for md_file in self.wiki_path.rglob("*.md"):
            file_content = md_file.read_text(encoding="utf-8")
            for _text, link_path in link_pattern.findall(file_content):
                if link_path.startswith("http"):
                    continue
                # Resolve relative to the file's directory
                resolved = (md_file.parent / link_path).resolve()
                if not resolved.exists():
                    rel_file = str(md_file.relative_to(self.wiki_path))
                    issues.append({
                        "type": "broken_link",
                        "detail": f"Link to '{link_path}' in '{rel_file}' points to non-existent file",
                        "file": rel_file,
                    })

        return issues

    def get_index(self) -> tuple[str, list[str]]:
        """Return index content and list of all wiki page paths."""
        index_path = self.wiki_path / "index.md"
        content = index_path.read_text(encoding="utf-8")

        pages: list[str] = []
        for subdir in ["entities", "topics", "summaries"]:
            dir_path = self.wiki_path / subdir
            if dir_path.exists():
                for page_file in dir_path.iterdir():
                    if page_file.suffix == ".md":
                        pages.append(f"{subdir}/{page_file.name}")

        return content, sorted(pages)

    def get_page(self, page_path: str) -> str | None:
        """Return content of a specific wiki page."""
        full_path = self.wiki_path / page_path
        if full_path.exists() and full_path.suffix == ".md":
            return full_path.read_text(encoding="utf-8")
        return None

    def get_log(self) -> list[str]:
        """Return log entries."""
        log_path = self.wiki_path / "log.md"
        content = log_path.read_text(encoding="utf-8")
        # Extract log entries (lines starting with '- [')
        entries = [line for line in content.split("\n") if line.startswith("- [")]
        return entries
