"""Tests for converter engines (Marker, Docling, OpenCV) and preprocessing."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from app.services.converter import ConversionEngine, ConversionResult, ConversionService
from app.services.preprocessing import PreprocessingService


# --- ConversionEngine enum tests ---


def test_conversion_engine_values():
    """Test ConversionEngine enum has expected values."""
    assert ConversionEngine.PYMUPDF == "pymupdf"
    assert ConversionEngine.MARKER == "marker"
    assert ConversionEngine.DOCLING == "docling"


def test_conversion_engine_from_string():
    """Test ConversionEngine can be created from string."""
    assert ConversionEngine("pymupdf") == ConversionEngine.PYMUPDF
    assert ConversionEngine("marker") == ConversionEngine.MARKER
    assert ConversionEngine("docling") == ConversionEngine.DOCLING


# --- ConversionService initialization tests ---


def test_conversion_service_default_engine():
    """Test ConversionService defaults to PyMuPDF engine."""
    service = ConversionService()
    assert service.preferred_engine == ConversionEngine.PYMUPDF


def test_conversion_service_marker_engine():
    """Test ConversionService can be initialized with Marker engine."""
    service = ConversionService(preferred_engine=ConversionEngine.MARKER)
    assert service.preferred_engine == ConversionEngine.MARKER


def test_conversion_service_docling_engine():
    """Test ConversionService can be initialized with Docling engine."""
    service = ConversionService(preferred_engine=ConversionEngine.DOCLING)
    assert service.preferred_engine == ConversionEngine.DOCLING


# --- Marker conversion tests ---


def test_convert_pdf_marker():
    """Test convert_pdf_marker with mocked marker internals."""
    mock_rendered = MagicMock()
    mock_rendered.markdown = "# Marker Result\n\nSome converted text."

    mock_converter_instance = MagicMock()
    mock_converter_instance.return_value = mock_rendered

    mock_converter_cls = MagicMock(return_value=mock_converter_instance)
    mock_create_models = MagicMock(return_value={"model": "dict"})

    with (
        patch("app.services.converter.MARKER_AVAILABLE", True),
        patch(
            "app.services.converter.create_model_dict",
            mock_create_models,
            create=True,
        ),
        patch(
            "app.services.converter.PdfConverter",
            mock_converter_cls,
            create=True,
        ),
    ):
        service = ConversionService(preferred_engine=ConversionEngine.MARKER)
        result = service.convert_pdf_marker(Path("/fake/doc.pdf"))

    assert isinstance(result, ConversionResult)
    assert result.markdown_content == "# Marker Result\n\nSome converted text."
    assert result.metadata["engine"] == "marker"
    mock_create_models.assert_called_once()
    mock_converter_cls.assert_called_once_with(artifact_dict={"model": "dict"})


@patch("app.services.converter.MARKER_AVAILABLE", False)
def test_convert_pdf_marker_not_available():
    """Test convert_pdf_marker raises RuntimeError when marker is not installed."""
    service = ConversionService(preferred_engine=ConversionEngine.MARKER)
    try:
        service.convert_pdf_marker(Path("/fake/doc.pdf"))
        assert False, "Should have raised RuntimeError"
    except RuntimeError as e:
        assert "marker-pdf is not installed" in str(e)


# --- Docling conversion tests ---


def test_convert_pdf_docling():
    """Test convert_pdf_docling with mocked docling internals."""
    mock_doc_result = MagicMock()
    mock_doc_result.document.export_to_markdown.return_value = (
        "# Docling Output\n\nConverted content."
    )

    mock_converter_instance = MagicMock()
    mock_converter_instance.convert.return_value = mock_doc_result
    mock_converter_cls = MagicMock(return_value=mock_converter_instance)

    with (
        patch("app.services.converter.DOCLING_AVAILABLE", True),
        patch(
            "app.services.converter.DocumentConverter",
            mock_converter_cls,
            create=True,
        ),
    ):
        service = ConversionService(preferred_engine=ConversionEngine.DOCLING)
        result = service.convert_pdf_docling(Path("/fake/doc.pdf"))

    assert isinstance(result, ConversionResult)
    assert result.markdown_content == "# Docling Output\n\nConverted content."
    assert result.metadata["engine"] == "docling"
    mock_converter_cls.assert_called_once()
    mock_converter_instance.convert.assert_called_once_with("/fake/doc.pdf")


@patch("app.services.converter.DOCLING_AVAILABLE", False)
def test_convert_pdf_docling_not_available():
    """Test convert_pdf_docling raises RuntimeError when docling is not installed."""
    service = ConversionService(preferred_engine=ConversionEngine.DOCLING)
    try:
        service.convert_pdf_docling(Path("/fake/doc.pdf"))
        assert False, "Should have raised RuntimeError"
    except RuntimeError as e:
        assert "docling is not installed" in str(e)


# --- Fallback mechanism tests ---


def test_fallback_marker_to_pymupdf():
    """Test fallback from Marker to PyMuPDF when Marker fails."""
    mock_create_models = MagicMock(side_effect=RuntimeError("Model loading failed"))

    with (
        patch("app.services.converter.MARKER_AVAILABLE", True),
        patch(
            "app.services.converter.create_model_dict",
            mock_create_models,
            create=True,
        ),
        patch(
            "app.services.converter.PdfConverter",
            MagicMock(),
            create=True,
        ),
    ):
        service = ConversionService(preferred_engine=ConversionEngine.MARKER)

        with patch.object(service, "_convert_pdf_pymupdf") as mock_pymupdf:
            mock_pymupdf.return_value = ConversionResult(
                markdown_content="PyMuPDF fallback content"
            )
            result = service.convert_pdf(Path("/fake/doc.pdf"))

    assert result.markdown_content == "PyMuPDF fallback content"
    mock_pymupdf.assert_called_once()


def test_fallback_docling_to_pymupdf():
    """Test fallback from Docling to PyMuPDF when Docling fails."""
    mock_converter_instance = MagicMock()
    mock_converter_instance.convert.side_effect = RuntimeError("Docling failed")
    mock_converter_cls = MagicMock(return_value=mock_converter_instance)

    with (
        patch("app.services.converter.DOCLING_AVAILABLE", True),
        patch(
            "app.services.converter.DocumentConverter",
            mock_converter_cls,
            create=True,
        ),
    ):
        service = ConversionService(preferred_engine=ConversionEngine.DOCLING)

        with patch.object(service, "_convert_pdf_pymupdf") as mock_pymupdf:
            mock_pymupdf.return_value = ConversionResult(
                markdown_content="PyMuPDF fallback content"
            )
            result = service.convert_pdf(Path("/fake/doc.pdf"))

    assert result.markdown_content == "PyMuPDF fallback content"
    mock_pymupdf.assert_called_once()


def test_pymupdf_engine_no_fallback():
    """Test PyMuPDF engine goes directly to _convert_pdf_pymupdf."""
    service = ConversionService(preferred_engine=ConversionEngine.PYMUPDF)

    with patch.object(service, "_convert_pdf_pymupdf") as mock_pymupdf:
        mock_pymupdf.return_value = ConversionResult(
            markdown_content="Direct PyMuPDF"
        )
        result = service.convert_pdf(Path("/fake/doc.pdf"))

    assert result.markdown_content == "Direct PyMuPDF"
    mock_pymupdf.assert_called_once()


# --- OpenCV preprocessing tests ---


def test_opencv_deskew_produces_valid_image():
    """Test opencv_deskew returns a valid PIL Image."""
    service = PreprocessingService()
    # Create a test image
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    result = service.opencv_deskew(img)
    assert isinstance(result, Image.Image)


def test_opencv_adaptive_threshold_produces_valid_image():
    """Test opencv_adaptive_threshold returns a valid PIL Image."""
    service = PreprocessingService()
    img = Image.new("RGB", (200, 200), color=(128, 128, 128))
    result = service.opencv_adaptive_threshold(img)
    assert isinstance(result, Image.Image)
    # Result should be binary (grayscale)
    assert result.mode == "L" or result.mode == "1" or len(np.array(result).shape) == 2


def test_opencv_morphological_denoise_produces_valid_image():
    """Test opencv_morphological_denoise returns a valid PIL Image."""
    service = PreprocessingService()
    img = Image.new("L", (200, 200), color=128)
    result = service.opencv_morphological_denoise(img)
    assert isinstance(result, Image.Image)


def test_opencv_pipeline_produces_valid_image():
    """Test opencv_pipeline chains all steps and returns a valid PIL Image."""
    service = PreprocessingService()
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    result = service.opencv_pipeline(img)
    assert isinstance(result, Image.Image)


def test_preprocess_pipeline_opencv_engine():
    """Test preprocess_pipeline with engine='opencv' uses opencv methods."""
    service = PreprocessingService()
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))

    with patch.object(service, "opencv_pipeline", wraps=service.opencv_pipeline) as mock_opencv:
        result = service.preprocess_pipeline(img, engine="opencv")
        mock_opencv.assert_called_once_with(img)

    assert isinstance(result, Image.Image)


def test_preprocess_pipeline_pillow_engine():
    """Test preprocess_pipeline with engine='pillow' uses pillow methods."""
    service = PreprocessingService()
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))

    with patch.object(service, "deskew_image", wraps=service.deskew_image) as mock_deskew:
        result = service.preprocess_pipeline(img, engine="pillow")
        mock_deskew.assert_called_once()

    assert isinstance(result, Image.Image)


def test_preprocess_pipeline_default_is_pillow():
    """Test preprocess_pipeline defaults to pillow engine."""
    service = PreprocessingService()
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))

    with patch.object(service, "opencv_pipeline") as mock_opencv:
        service.preprocess_pipeline(img)
        mock_opencv.assert_not_called()


# --- convert_image_opencv tests ---


@patch("app.services.converter.ConversionService.convert_image_opencv")
def test_convert_image_opencv_method_exists(mock_method):
    """Test convert_image_opencv method exists on ConversionService."""
    service = ConversionService()
    assert hasattr(service, "convert_image_opencv")


def test_convert_image_opencv_with_mocked_tesseract(tmp_path):
    """Test convert_image_opencv uses opencv preprocessing and pytesseract."""
    # Create a test image file
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img_path = tmp_path / "test.png"
    img.save(img_path)

    service = ConversionService()

    with patch("app.services.converter.PreprocessingService.preprocess_pipeline") as mock_preprocess:
        mock_preprocess.return_value = img
        with patch.dict("sys.modules", {"pytesseract": MagicMock()}):
            import sys

            mock_pytesseract = sys.modules["pytesseract"]
            mock_pytesseract.image_to_string.return_value = "OCR text from opencv"

            # We need to patch inside the method scope
            with patch(
                "pytesseract.image_to_string", return_value="OCR text from opencv"
            ):
                result = service.convert_image_opencv(img_path)

    assert isinstance(result, ConversionResult)


def test_convert_image_opencv_calls_opencv_pipeline(tmp_path):
    """Test convert_image_opencv calls preprocessing with opencv engine."""
    # Create a test image file
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    img_path = tmp_path / "test.png"
    img.save(img_path)

    service = ConversionService()

    with patch.object(
        service.preprocessing, "preprocess_pipeline", return_value=img
    ) as mock_pipeline:
        # pytesseract will fail, but that's ok - we just check pipeline is called
        service.convert_image_opencv(img_path)
        mock_pipeline.assert_called_once()
        # Verify it was called with engine="opencv"
        call_args = mock_pipeline.call_args
        assert call_args[1].get("engine") == "opencv" or (
            len(call_args[0]) > 1 and call_args[0][1] == "opencv"
        )
