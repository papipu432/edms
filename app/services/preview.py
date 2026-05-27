import io
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class PreviewService:
    """Generates and caches document previews."""

    def generate_pdf_preview(self, file_path: Path) -> bytes | None:
        """Render first page of a PDF as a PNG thumbnail (max 800px width)."""
        try:
            import fitz

            doc = fitz.open(str(file_path))
            page = doc[0]
            # Scale to max 800px width
            page_width = page.rect.width
            scale = min(800 / page_width, 2.0) if page_width > 0 else 2.0
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
            png_bytes = pix.tobytes("png")
            doc.close()
            return png_bytes
        except Exception as e:
            logger.warning("PDF preview generation failed for %s: %s", file_path, e)
            return None

    def generate_markdown_preview(self, markdown_content: str, max_chars: int = 2000) -> str:
        """Convert first max_chars of markdown to basic HTML."""
        content = markdown_content[:max_chars]

        # Escape HTML entities
        content = content.replace("&", "&amp;")
        content = content.replace("<", "&lt;")
        content = content.replace(">", "&gt;")

        # Convert markdown to HTML with basic regex
        lines = content.split("\n")
        html_lines = []
        in_list = False

        for line in lines:
            stripped = line.strip()

            # Headers
            if stripped.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h3>{stripped[4:]}</h3>")
            elif stripped.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h2>{stripped[3:]}</h2>")
            elif stripped.startswith("# "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h1>{stripped[2:]}</h1>")
            elif stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                html_lines.append(f"<li>{stripped[2:]}</li>")
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                if stripped:
                    html_lines.append(f"<p>{stripped}</p>")

        if in_list:
            html_lines.append("</ul>")

        body = "\n".join(html_lines)

        # Inline formatting
        body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body)
        body = re.sub(r"\*(.+?)\*", r"<em>\1</em>", body)
        body = re.sub(r"`(.+?)`", r"<code>\1</code>", body)
        body = re.sub(
            r"\[(.+?)\]\((.+?)\)",
            lambda m: self._safe_link(m.group(1), m.group(2)),
            body,
        )

        html = f"""<!DOCTYPE html>
<html>
<head>
<style>
body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
h1, h2, h3 {{ color: #333; }}
code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; }}
ul {{ padding-left: 20px; }}
</style>
</head>
<body>
{body}
</body>
</html>"""
        return html

    def _safe_link(self, text: str, href: str) -> str:
        """Validate link href and return safe HTML anchor or plain text.

        Only allows http://, https://, and relative paths. Rejects dangerous
        schemes like javascript:, data:, vbscript:.
        """
        href_stripped = href.strip().lower()
        # Allow http, https, and relative paths (no scheme)
        if href_stripped.startswith(("http://", "https://")) or (
            ":" not in href_stripped.split("/")[0]
            and not href_stripped.startswith("//")
        ):
            return f'<a href="{href}">{text}</a>'
        # Reject dangerous schemes
        return text

    def generate_image_preview(self, file_path: Path) -> bytes | None:
        """Create a thumbnail of an image (max 400x400)."""
        try:
            from PIL import Image

            img = Image.open(file_path)
            img.thumbnail((400, 400))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            logger.warning("Image preview generation failed for %s: %s", file_path, e)
            return None

    def get_preview_path(self, document_id: int) -> Path:
        """Return the conventional PNG preview cache path."""
        return Path(f"data/previews/{document_id}_preview.png")

    def get_html_preview_path(self, document_id: int) -> Path:
        """Return the conventional HTML preview cache path."""
        return Path(f"data/previews/{document_id}_preview.html")

    def generate_and_cache(
        self,
        document_id: int,
        file_path: Path,
        file_type: str,
        markdown_content: str | None = None,
    ) -> str | None:
        """Generate appropriate preview based on file type and cache to disk."""
        # Ensure previews directory exists
        previews_dir = Path("data/previews")
        previews_dir.mkdir(parents=True, exist_ok=True)

        file_type_lower = file_type.lower()
        suffix = file_path.suffix.lower() if file_path.suffix else ""

        # Determine preview type and generate
        if "pdf" in file_type_lower or suffix == ".pdf":
            png_bytes = self.generate_pdf_preview(file_path)
            if png_bytes:
                cache_path = self.get_preview_path(document_id)
                cache_path.write_bytes(png_bytes)
                return str(cache_path)

        elif file_type_lower.startswith("image/") or suffix in (
            ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp",
        ):
            png_bytes = self.generate_image_preview(file_path)
            if png_bytes:
                cache_path = self.get_preview_path(document_id)
                cache_path.write_bytes(png_bytes)
                return str(cache_path)

        # For markdown/text-based previews
        if markdown_content:
            html = self.generate_markdown_preview(markdown_content)
            cache_path = self.get_html_preview_path(document_id)
            cache_path.write_text(html, encoding="utf-8")
            return str(cache_path)

        return None
