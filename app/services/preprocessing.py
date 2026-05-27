import logging

from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)


class PreprocessingService:
    """Image preprocessing for OCR quality improvement."""

    def deskew_image(self, image: Image.Image) -> Image.Image:
        """Attempt to deskew an image using a simple rotation heuristic.

        If pytesseract OSD is available, use it for rotation detection.
        Otherwise, return the image unchanged.
        """
        try:
            import pytesseract

            osd = pytesseract.image_to_osd(image)
            rotation = 0
            for line in osd.splitlines():
                if "Rotate:" in line:
                    rotation = int(line.split(":")[1].strip())
                    break
            if rotation != 0:
                image = image.rotate(-rotation, expand=True)
        except Exception:
            logger.debug("OSD-based deskew unavailable, skipping deskew")
        return image

    def enhance_image(self, image: Image.Image) -> Image.Image:
        """Enhance image contrast for better OCR results."""
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(1.5)

    def denoise_image(self, image: Image.Image) -> Image.Image:
        """Apply median filter to reduce noise."""
        return image.filter(ImageFilter.MedianFilter(size=3))

    def preprocess_pipeline(self, image: Image.Image) -> Image.Image:
        """Chain all preprocessing steps."""
        image = self.deskew_image(image)
        image = self.enhance_image(image)
        image = self.denoise_image(image)
        return image
