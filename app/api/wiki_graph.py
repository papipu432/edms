"""API endpoints for wiki graph visualization data."""

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/wiki/graph", tags=["wiki-graph"])


def _get_page_type(path: str) -> str:
    """Determine the page type from its path."""
    if path.startswith("entities/"):
        return "entity"
    elif path.startswith("topics/"):
        return "topic"
    elif path.startswith("summaries/"):
        return "summary"
    return "unknown"


def _get_color(page_type: str) -> str:
    """Get color for a page type."""
    colors = {
        "entity": "#3b82f6",
        "topic": "#10b981",
        "summary": "#f59e0b",
    }
    return colors.get(page_type, "#6b7280")


@router.get("/data")
async def get_wiki_graph_data(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return nodes and edges for the wiki graph visualization.

    Reads all wiki pages, extracts markdown links, and returns
    nodes (color-coded by type) and edges.
    """
    return await asyncio.to_thread(_build_graph_data)


def _build_graph_data() -> dict:
    """Build graph data synchronously (run in thread to avoid blocking event loop)."""
    wiki_path = Path(settings.WIKI_PATH)

    nodes = []
    edges = []
    page_paths: list[str] = []

    # Collect all pages
    for subdir in ["entities", "topics", "summaries"]:
        dir_path = wiki_path / subdir
        if dir_path.exists():
            for f in dir_path.iterdir():
                if f.suffix == ".md":
                    rel_path = f"{subdir}/{f.name}"
                    page_paths.append(rel_path)

    # Build node list
    path_to_id: dict[str, int] = {}
    for idx, path in enumerate(sorted(page_paths)):
        page_type = _get_page_type(path)
        label = Path(path).stem
        node = {
            "id": idx,
            "label": label,
            "type": page_type,
            "color": _get_color(page_type),
            "path": path,
        }
        nodes.append(node)
        path_to_id[path] = idx

    # Extract links and build edges
    link_pattern = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    for path in sorted(page_paths):
        full_path = wiki_path / path
        content = full_path.read_text(encoding="utf-8")
        source_id = path_to_id[path]

        for _text, link_target in link_pattern.findall(content):
            if link_target.startswith("http"):
                continue
            # Resolve relative link
            resolved = (full_path.parent / link_target).resolve()
            try:
                rel_resolved = str(resolved.relative_to(wiki_path.resolve()))
            except ValueError:
                continue

            if rel_resolved in path_to_id:
                target_id = path_to_id[rel_resolved]
                edges.append({"source": source_id, "target": target_id})

    return {"nodes": nodes, "edges": edges}
