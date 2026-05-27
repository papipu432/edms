import logging

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

try:
    import cv2

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.info("OpenCV not available; opencv preprocessing methods will not work.")


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

    def preprocess_pipeline(
        self, image: Image.Image, engine: str = "pillow"
    ) -> Image.Image:
        """Chain all preprocessing steps using the specified engine.

        Args:
            image: PIL Image to preprocess.
            engine: 'pillow' (default) or 'opencv'.

        Returns:
            Preprocessed PIL Image.
        """
        if engine == "opencv":
            return self.opencv_pipeline(image)
        # Default: pillow pipeline
        image = self.deskew_image(image)
        image = self.enhance_image(image)
        image = self.denoise_image(image)
        return image

    # --- OpenCV-based methods ---

    def opencv_deskew(self, image: Image.Image) -> Image.Image:
        """Deskew an image using Hough line transform to detect skew angle."""
        if not OPENCV_AVAILABLE:
            logger.warning("OpenCV not available, skipping deskew")
            return image

        img_array = np.array(image)

        # Convert to grayscale if needed
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        # Edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Detect lines using Hough transform
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10
        )

        if lines is None:
            return image

        # Calculate median angle from detected lines
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Only consider near-horizontal lines (within 45 degrees)
            if abs(angle) < 45:
                angles.append(angle)

        if not angles:
            return image

        median_angle = float(np.median(angles))

        # Only correct if skew is significant (> 0.5 degrees)
        if abs(median_angle) < 0.5:
            return image

        # Rotate to correct skew
        (h, w) = img_array.shape[:2]
        center = (w // 2, h // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(
            img_array, rotation_matrix, (w, h), borderValue=(255, 255, 255)
        )

        return Image.fromarray(rotated)

    def opencv_adaptive_threshold(self, image: Image.Image) -> Image.Image:
        """Apply adaptive thresholding for binarization."""
        if not OPENCV_AVAILABLE:
            logger.warning("OpenCV not available, skipping adaptive threshold")
            return image

        img_array = np.array(image)

        # Convert to grayscale if needed
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        # Apply adaptive threshold
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        return Image.fromarray(binary)

    def opencv_morphological_denoise(self, image: Image.Image) -> Image.Image:
        """Apply morphological open/close operations to reduce noise."""
        if not OPENCV_AVAILABLE:
            logger.warning("OpenCV not available, skipping morphological denoise")
            return image

        img_array = np.array(image)

        # Convert to grayscale if needed
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array

        # Create kernel for morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))

        # Opening (erosion followed by dilation) removes small noise
        opened = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)

        # Closing (dilation followed by erosion) fills small holes
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel)

        return Image.fromarray(closed)

    def opencv_pipeline(self, image: Image.Image) -> Image.Image:
        """OpenCV preprocessing pipeline: grayscale, adaptive threshold,
        morphological denoise, deskew."""
        if not OPENCV_AVAILABLE:
            logger.warning(
                "OpenCV not available, falling back to pillow pipeline"
            )
            return self.preprocess_pipeline(image, engine="pillow")

        # Convert to grayscale first (via adaptive threshold which handles it)
        image = self.opencv_adaptive_threshold(image)
        image = self.opencv_morphological_denoise(image)
        image = self.opencv_deskew(image)
        return image
