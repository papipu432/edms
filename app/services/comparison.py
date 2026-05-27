import difflib
from typing import Any

from app.models.document import Document


class ComparisonService:
    """Service for comparing documents and their content."""

    def compare_metadata(self, doc_a: Document, doc_b: Document) -> list[dict[str, Any]]:
        """Field-by-field comparison of two documents' metadata."""
        fields_to_compare = [
            "original_filename",
            "file_size",
            "file_type",
            "status",
            "summary",
            "keywords",
            "created_at",
            "updated_at",
        ]
        results = []
        for field in fields_to_compare:
            val_a = getattr(doc_a, field, None)
            val_b = getattr(doc_b, field, None)
            # Convert enums to their value for comparison
            if hasattr(val_a, "value"):
                val_a = val_a.value
            if hasattr(val_b, "value"):
                val_b = val_b.value
            # Convert datetime to isoformat string for serialization
            if hasattr(val_a, "isoformat"):
                val_a = val_a.isoformat()
            if hasattr(val_b, "isoformat"):
                val_b = val_b.isoformat()
            results.append({
                "field": field,
                "doc_a_value": val_a,
                "doc_b_value": val_b,
                "differs": val_a != val_b,
            })
        return results

    def compare_markdown_content(self, content_a: str, content_b: str) -> dict[str, Any]:
        """Compare two markdown content strings and return diff information."""
        lines_a = content_a.splitlines(keepends=True)
        lines_b = content_b.splitlines(keepends=True)

        # Generate unified diff
        diff_lines = list(difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile="Document A",
            tofile="Document B",
        ))
        unified_diff = "".join(diff_lines)

        # Count additions and deletions (skip the header lines starting with --- and +++)
        additions_count = 0
        deletions_count = 0
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                additions_count += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions_count += 1

        # Calculate similarity ratio
        matcher = difflib.SequenceMatcher(None, lines_a, lines_b)
        similarity_ratio = matcher.ratio()

        return {
            "unified_diff": unified_diff,
            "additions_count": additions_count,
            "deletions_count": deletions_count,
            "similarity_ratio": round(similarity_ratio, 4),
        }

    def generate_diff_html(
        self,
        content_a: str,
        content_b: str,
        label_a: str = "Document A",
        label_b: str = "Document B",
    ) -> str:
        """Generate side-by-side HTML diff using difflib.HtmlDiff."""
        lines_a = content_a.splitlines()
        lines_b = content_b.splitlines()

        html_diff = difflib.HtmlDiff()
        table = html_diff.make_table(
            lines_a,
            lines_b,
            fromdesc=label_a,
            todesc=label_b,
            context=True,
            numlines=5,
        )
        return table

    def compare_versions_content(
        self,
        content_a: str | None,
        content_b: str | None,
        meta_a: dict[str, Any],
        meta_b: dict[str, Any],
    ) -> dict[str, Any]:
        """Combine metadata comparison and content diff for version comparison."""
        result: dict[str, Any] = {
            "metadata": {
                "version_a": meta_a,
                "version_b": meta_b,
            },
            "content_diff": None,
            "has_content_diff": False,
        }

        if content_a is not None and content_b is not None:
            result["content_diff"] = self.compare_markdown_content(content_a, content_b)
            result["has_content_diff"] = True

        return result
