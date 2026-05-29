"""Offline package generation service."""

import json
import zipfile
from io import BytesIO
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.group import Group


class OfflinePackageService:
    """Generates self-contained offline packages as ZIP archives."""

    async def generate_package(
        self,
        db: AsyncSession,
        document_ids: list[int] | None = None,
        group_id: int | None = None,
    ) -> BytesIO:
        """Generate an offline package ZIP containing documents and a viewer."""
        documents = await self._get_documents(db, document_ids, group_id)
        metadata = []
        buffer = BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for doc in documents:
                doc_meta = {
                    "id": doc.id,
                    "filename": doc.original_filename,
                    "file_type": doc.file_type,
                    "file_size": doc.file_size,
                    "status": doc.status.value if doc.status else "unknown",
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "group_id": doc.group_id,
                }
                metadata.append(doc_meta)

                # Add the file to the ZIP if it exists on disk
                storage_path = Path(doc.storage_path)
                if storage_path.exists():
                    zf.write(storage_path, f"documents/{doc.original_filename}")
                else:
                    # Create a placeholder
                    zf.writestr(
                        f"documents/{doc.original_filename}",
                        f"[File not available: {doc.original_filename}]",
                    )

                # Add markdown content if available
                if doc.markdown_path:
                    md_path = Path(doc.markdown_path)
                    if md_path.exists():
                        zf.write(md_path, f"documents/{doc.original_filename}.md")

            # Write metadata.json
            zf.writestr("metadata.json", json.dumps(metadata, indent=2))

            # Write search index
            search_index = [
                {"id": m["id"], "filename": m["filename"], "type": m["file_type"]}
                for m in metadata
            ]
            zf.writestr("search_index.json", json.dumps(search_index, indent=2))

            # Write self-contained HTML viewer
            zf.writestr("index.html", self._generate_viewer_html(metadata))

        buffer.seek(0)
        return buffer

    async def _get_documents(
        self,
        db: AsyncSession,
        document_ids: list[int] | None = None,
        group_id: int | None = None,
    ) -> list[Document]:
        """Fetch documents by IDs or group."""
        if document_ids:
            result = await db.execute(
                select(Document).where(Document.id.in_(document_ids))
            )
        elif group_id:
            result = await db.execute(
                select(Document).where(Document.group_id == group_id)
            )
        else:
            result = await db.execute(select(Document).limit(100))
        return list(result.scalars().all())

    def _generate_viewer_html(self, metadata: list[dict]) -> str:
        """Generate a self-contained HTML viewer with inline CSS/JS."""
        doc_items = ""
        for doc in metadata:
            doc_items += (
                f'<div class="doc-item" data-id="{doc["id"]}" '
                f'data-filename="{doc["filename"]}" data-type="{doc["file_type"]}">'
                f'<span class="doc-name">{doc["filename"]}</span>'
                f'<span class="doc-type">{doc["file_type"]}</span>'
                f'</div>\n'
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EDMS Offline Viewer</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; display: flex; height: 100vh; }}
.sidebar {{ width: 300px; background: #f5f5f5; border-right: 1px solid #ddd; overflow-y: auto; padding: 16px; }}
.main {{ flex: 1; padding: 24px; overflow-y: auto; }}
.search-box {{ width: 100%; padding: 8px; margin-bottom: 16px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }}
.doc-item {{ padding: 8px; margin: 4px 0; cursor: pointer; border-radius: 4px; border: 1px solid #e0e0e0; background: #fff; }}
.doc-item:hover {{ background: #e3f2fd; }}
.doc-item.active {{ background: #bbdefb; }}
.doc-name {{ display: block; font-weight: 500; }}
.doc-type {{ display: block; font-size: 12px; color: #666; }}
h1 {{ margin-top: 0; }}
.detail-table {{ width: 100%; border-collapse: collapse; }}
.detail-table td {{ padding: 8px; border-bottom: 1px solid #eee; }}
.detail-table td:first-child {{ font-weight: 500; width: 120px; }}
</style>
</head>
<body>
<div class="sidebar">
<h2>Documents</h2>
<input type="text" class="search-box" id="search" placeholder="Search documents...">
<div id="doc-list">
{doc_items}
</div>
</div>
<div class="main" id="detail">
<h1>EDMS Offline Viewer</h1>
<p>Select a document from the sidebar to view its details.</p>
<p>Total documents: {len(metadata)}</p>
</div>
<script>
const docs = {json.dumps(metadata)};
const searchBox = document.getElementById('search');
const docList = document.getElementById('doc-list');
const detail = document.getElementById('detail');

searchBox.addEventListener('input', function() {{
    const q = this.value.toLowerCase();
    document.querySelectorAll('.doc-item').forEach(function(el) {{
        const name = el.dataset.filename.toLowerCase();
        el.style.display = name.includes(q) ? '' : 'none';
    }});
}});

docList.addEventListener('click', function(e) {{
    const item = e.target.closest('.doc-item');
    if (!item) return;
    document.querySelectorAll('.doc-item').forEach(el => el.classList.remove('active'));
    item.classList.add('active');
    const id = parseInt(item.dataset.id);
    const doc = docs.find(d => d.id === id);
    if (doc) {{
        detail.innerHTML = '<h1>' + doc.filename + '</h1>' +
            '<table class="detail-table">' +
            '<tr><td>ID</td><td>' + doc.id + '</td></tr>' +
            '<tr><td>Type</td><td>' + doc.file_type + '</td></tr>' +
            '<tr><td>Size</td><td>' + doc.file_size + ' bytes</td></tr>' +
            '<tr><td>Status</td><td>' + doc.status + '</td></tr>' +
            '<tr><td>Created</td><td>' + (doc.created_at || 'N/A') + '</td></tr>' +
            '<tr><td>Group ID</td><td>' + doc.group_id + '</td></tr>' +
            '</table>';
    }}
}});
</script>
</body>
</html>"""
