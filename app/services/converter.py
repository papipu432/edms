import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from app.services.preprocessing import PreprocessingService

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    markdown_content: str = ""
    tables: list[str] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class ConversionService:
    """Converts documents to Markdown, extracting tables and images."""

    def __init__(self) -> None:
        self.preprocessing = PreprocessingService()

    def convert_pdf(self, file_path: Path) -> ConversionResult:
        """Extract text, images, and tables from a PDF using pymupdf."""
        import fitz

        result = ConversionResult()
        markdown_parts: list[str] = []

        try:
            doc = fitz.open(str(file_path))
            for page_num, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    markdown_parts.append(f"## Page {page_num + 1}\n\n{text.strip()}")

                # Extract images from page
                for img_index, img in enumerate(page.get_images(full=True)):
                    try:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        if base_image:
                            image_bytes = base_image["image"]
                            pil_image = Image.open(io.BytesIO(image_bytes))
                            # Save to temp location; pipeline will move it
                            result.images.append(pil_image)  # type: ignore[arg-type]
                    except Exception:
                        logger.debug(
                            "Failed to extract image %d from page %d",
                            img_index,
                            page_num,
                        )

            doc.close()
        except Exception as e:
            logger.error("PDF conversion error: %s", e)
            result.metadata["error"] = str(e)

        # If no text was extracted, try OCR
        if not any(part.strip() for part in markdown_parts):
            ocr_result = self._ocr_pdf_pages(file_path)
            if ocr_result:
                markdown_parts = [ocr_result]
                result.metadata["ocr_used"] = True

        result.markdown_content = "\n\n".join(markdown_parts)
        return result

    def _ocr_pdf_pages(self, file_path: Path) -> str:
        """Attempt OCR on PDF pages as a fallback."""
        try:
            import fitz
            import pytesseract

            doc = fitz.open(str(file_path))
            ocr_parts: list[str] = []
            for page_num, page in enumerate(doc):
                pix = page.get_pixmap()
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img = self.preprocessing.preprocess_pipeline(img)
                text = pytesseract.image_to_string(img)
                if text.strip():
                    ocr_parts.append(f"## Page {page_num + 1}\n\n{text.strip()}")
            doc.close()
            return "\n\n".join(ocr_parts)
        except Exception as e:
            logger.warning("OCR fallback failed (tesseract may not be installed): %s", e)
            return ""

    def convert_docx(self, file_path: Path) -> ConversionResult:
        """Extract text and images from a DOCX file."""
        from docx import Document

        result = ConversionResult()
        markdown_parts: list[str] = []

        try:
            doc = Document(str(file_path))

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                # Map heading styles to markdown
                if para.style and para.style.name.startswith("Heading"):
                    try:
                        level = int(para.style.name.replace("Heading ", ""))
                    except (ValueError, AttributeError):
                        level = 1
                    markdown_parts.append(f"{'#' * level} {text}")
                else:
                    markdown_parts.append(text)

            # Extract images from document relationships
            for rel in doc.part.rels.values():
                if "image" in rel.reltype:
                    try:
                        image_data = rel.target_part.blob
                        pil_image = Image.open(io.BytesIO(image_data))
                        result.images.append(pil_image)  # type: ignore[arg-type]
                    except Exception:
                        logger.debug("Failed to extract image from DOCX")

        except Exception as e:
            logger.error("DOCX conversion error: %s", e)
            result.metadata["error"] = str(e)

        result.markdown_content = "\n\n".join(markdown_parts)
        return result

    def convert_image(self, file_path: Path) -> ConversionResult:
        """OCR an image file using pytesseract with preprocessing."""
        result = ConversionResult()

        try:
            image = Image.open(file_path)
            # Convert to RGB if necessary
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            processed = self.preprocessing.preprocess_pipeline(image)

            try:
                import pytesseract

                text = pytesseract.image_to_string(processed)
                result.markdown_content = text.strip()
            except Exception as e:
                logger.warning(
                    "Tesseract not available for image OCR: %s", e
                )
                result.metadata["warning"] = "tesseract not available"
                result.markdown_content = ""

        except Exception as e:
            logger.error("Image conversion error: %s", e)
            result.metadata["error"] = str(e)

        return result
