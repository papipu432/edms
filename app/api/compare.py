from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.document import Document
from app.models.user import User
from app.models.version import DocumentVersion
from app.schemas.comparison import (
    ComparisonResponse,
    ContentDiffResponse,
    MetadataComparisonResponse,
    MetadataField,
)
from app.services.comparison import ComparisonService

router = APIRouter(tags=["compare"])

comparison_service = ComparisonService()


def _read_markdown(markdown_path: str | None) -> str | None:
    """Read markdown content from a file path, returning None if not available."""
    if not markdown_path:
        return None
    path = Path(markdown_path)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


@router.get("/api/documents/compare", response_model=ComparisonResponse)
async def compare_documents(
    doc_a: int = Query(..., description="ID of first document"),
    doc_b: int = Query(..., description="ID of second document"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComparisonResponse:
    """Compare two documents: metadata and optionally content."""
    document_a = await db.get(Document, doc_a)
    if not document_a:
        raise HTTPException(status_code=404, detail="Document A not found")

    document_b = await db.get(Document, doc_b)
    if not document_b:
        raise HTTPException(status_code=404, detail="Document B not found")

    # Compare metadata
    metadata_fields = comparison_service.compare_metadata(document_a, document_b)
    metadata = MetadataComparisonResponse(
        fields=[MetadataField(**f) for f in metadata_fields]
    )

    # Try to compare content if both have markdown
    content_diff = None
    has_content_diff = False

    content_a = _read_markdown(document_a.markdown_path)
    content_b = _read_markdown(document_b.markdown_path)

    if content_a is not None and content_b is not None:
        diff_result = comparison_service.compare_markdown_content(content_a, content_b)
        content_diff = ContentDiffResponse(**diff_result)
        has_content_diff = True

    return ComparisonResponse(
        metadata=metadata,
        content_diff=content_diff,
        has_content_diff=has_content_diff,
    )


@router.get("/api/documents/{document_id}/versions/diff", response_model=ContentDiffResponse)
async def compare_document_versions(
    document_id: int,
    version_a: int = Query(..., description="Version number A"),
    version_b: int = Query(..., description="Version number B"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContentDiffResponse:
    """Compare content of two versions of the same document."""
    document = await db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load version records
    from sqlalchemy import select

    result_a = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_a,
        )
    )
    ver_a = result_a.scalar_one_or_none()
    if not ver_a:
        raise HTTPException(
            status_code=404, detail=f"Version {version_a} not found"
        )

    result_b = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version_number == version_b,
        )
    )
    ver_b = result_b.scalar_one_or_none()
    if not ver_b:
        raise HTTPException(
            status_code=404, detail=f"Version {version_b} not found"
        )

    # Try to read markdown content from version storage paths
    content_a = _read_markdown(ver_a.storage_path)
    content_b = _read_markdown(ver_b.storage_path)

    if content_a is None:
        content_a = ""
    if content_b is None:
        content_b = ""

    diff_result = comparison_service.compare_markdown_content(content_a, content_b)
    return ContentDiffResponse(**diff_result)


@router.get("/api/documents/compare/html", response_class=HTMLResponse)
async def compare_documents_html(
    doc_a: int = Query(..., description="ID of first document"),
    doc_b: int = Query(..., description="ID of second document"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Return an HTML page with side-by-side comparison of two documents."""
    document_a = await db.get(Document, doc_a)
    if not document_a:
        raise HTTPException(status_code=404, detail="Document A not found")

    document_b = await db.get(Document, doc_b)
    if not document_b:
        raise HTTPException(status_code=404, detail="Document B not found")

    # Compare metadata
    metadata_fields = comparison_service.compare_metadata(document_a, document_b)

    # Try to get content diff
    content_a = _read_markdown(document_a.markdown_path)
    content_b = _read_markdown(document_b.markdown_path)

    diff_table = ""
    if content_a is not None and content_b is not None:
        diff_table = comparison_service.generate_diff_html(
            content_a,
            content_b,
            label_a=document_a.original_filename,
            label_b=document_b.original_filename,
        )

    # Build HTML response
    html = _build_comparison_html(
        document_a=document_a,
        document_b=document_b,
        metadata_fields=metadata_fields,
        diff_table=diff_table,
    )
    return HTMLResponse(content=html)


def _build_comparison_html(
    document_a: Document,
    document_b: Document,
    metadata_fields: list[dict],
    diff_table: str,
) -> str:
    """Build a complete HTML page for document comparison."""
    metadata_rows = ""
    for field in metadata_fields:
        differs_class = 'class="bg-red-50"' if field["differs"] else ""
        metadata_rows += f"""
        <tr {differs_class}>
            <td class="px-4 py-2 font-medium border">{field["field"]}</td>
            <td class="px-4 py-2 border">{field["doc_a_value"]}</td>
            <td class="px-4 py-2 border">{field["doc_b_value"]}</td>
            <td class="px-4 py-2 border text-center">{"Yes" if field["differs"] else "No"}</td>
        </tr>"""

    content_section = ""
    if diff_table:
        content_section = f"""
        <div class="mt-8">
            <h2 class="text-xl font-bold mb-4">Content Comparison</h2>
            <div class="overflow-x-auto border rounded">
                {diff_table}
            </div>
        </div>"""
    else:
        content_section = """
        <div class="mt-8">
            <h2 class="text-xl font-bold mb-4">Content Comparison</h2>
            <p class="text-gray-500">No markdown content available for comparison.</p>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document Comparison</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        table.diff {{ font-family: monospace; white-space: pre-wrap; width: 100%; }}
        .diff_add {{ background-color: #dcfce7; }}
        .diff_sub {{ background-color: #fee2e2; }}
        .diff_chg {{ background-color: #fef9c3; }}
        td.diff_header {{ font-weight: bold; background-color: #f3f4f6; }}
    </style>
</head>
<body class="bg-gray-50 p-6">
    <div class="max-w-7xl mx-auto">
        <h1 class="text-2xl font-bold mb-6">Document Comparison</h1>
        <p class="mb-4 text-gray-600">
            Comparing <strong>{document_a.original_filename}</strong> (ID: {document_a.id})
            with <strong>{document_b.original_filename}</strong> (ID: {document_b.id})
        </p>

        <div>
            <h2 class="text-xl font-bold mb-4">Metadata Comparison</h2>
            <table class="w-full border-collapse border">
                <thead>
                    <tr class="bg-gray-100">
                        <th class="px-4 py-2 border text-left">Field</th>
                        <th class="px-4 py-2 border text-left">Document A</th>
                        <th class="px-4 py-2 border text-left">Document B</th>
                        <th class="px-4 py-2 border text-center">Differs</th>
                    </tr>
                </thead>
                <tbody>
                    {metadata_rows}
                </tbody>
            </table>
        </div>

        {content_section}
    </div>
</body>
</html>"""
