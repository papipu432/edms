"""Watermark service for applying watermarks to documents."""

import io
import math
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.watermark import WatermarkConfig


class WatermarkService:
    """Service for watermarking documents."""

    async def get_config_for_group(
        self, db: AsyncSession, group_id: int | None
    ) -> WatermarkConfig | None:
        """Find group-specific config or fall back to global config."""
        if group_id is not None:
            result = await db.execute(
                select(WatermarkConfig).where(
                    WatermarkConfig.group_id == group_id,
                    WatermarkConfig.enabled.is_(True),
                )
            )
            config = result.scalar_one_or_none()
            if config:
                return config

        # Fall back to global config (group_id is None)
        result = await db.execute(
            select(WatermarkConfig).where(
                WatermarkConfig.group_id.is_(None),
                WatermarkConfig.enabled.is_(True),
            )
        )
        return result.scalar_one_or_none()

    def render_text(
        self,
        template: str,
        user: str = "",
        doc_id: str = "",
        custom_text: str = "",
    ) -> str:
        """Substitute variables in watermark text template.

        Uses str.replace() instead of str.format() to avoid format string
        injection when user-controlled values contain format specifiers.
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        text = template.replace("{user}", user)
        text = text.replace("{timestamp}", timestamp)
        text = text.replace("{doc_id}", str(doc_id))
        text = text.replace("{custom_text}", custom_text or "")
        return text

    def apply_pdf_watermark(
        self,
        pdf_bytes: bytes,
        text: str,
        opacity: float = 0.3,
        position: str = "diagonal",
    ) -> bytes:
        """Apply a text watermark to a PDF using pikepdf and Pillow."""
        import pikepdf
        from PIL import Image, ImageDraw, ImageFont

        # Open the source PDF
        pdf = pikepdf.open(io.BytesIO(pdf_bytes))

        for page in pdf.pages:
            # Get page dimensions
            mediabox = page.get("/MediaBox", [0, 0, 612, 792])
            width = float(mediabox[2]) - float(mediabox[0])
            height = float(mediabox[3]) - float(mediabox[1])

            # Create watermark image with transparency
            img_width = int(width * 2)
            img_height = int(height * 2)
            watermark_img = Image.new("RGBA", (img_width, img_height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(watermark_img)

            # Use default font
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
            except (OSError, IOError):
                font = ImageFont.load_default()

            alpha = int(opacity * 255)

            if position == "diagonal":
                # Draw text diagonally across the page
                angle = -45
                temp_img = Image.new("RGBA", (img_width * 2, img_height * 2), (255, 255, 255, 0))
                temp_draw = ImageDraw.Draw(temp_img)
                # Repeat text across the page
                for y in range(0, img_height * 2, 200):
                    for x in range(-img_width, img_width * 2, 400):
                        temp_draw.text((x, y), text, fill=(128, 128, 128, alpha), font=font)
                rotated = temp_img.rotate(angle, expand=False, center=(img_width, img_height))
                # Crop back to original size
                left = (rotated.width - img_width) // 2
                top = (rotated.height - img_height) // 2
                watermark_img = rotated.crop((left, top, left + img_width, top + img_height))
            elif position == "center":
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                x = (img_width - tw) // 2
                y = (img_height - th) // 2
                draw.text((x, y), text, fill=(128, 128, 128, alpha), font=font)
            elif position == "top":
                draw.text((20, 20), text, fill=(128, 128, 128, alpha), font=font)
            elif position == "bottom":
                bbox = draw.textbbox((0, 0), text, font=font)
                th = bbox[3] - bbox[1]
                draw.text((20, img_height - th - 20), text, fill=(128, 128, 128, alpha), font=font)

            # Convert watermark image to PDF page using pikepdf
            img_buffer = io.BytesIO()
            watermark_img = watermark_img.convert("RGBA")
            watermark_img.save(img_buffer, format="PNG")
            img_buffer.seek(0)

            # Create a single-page PDF from the watermark image
            wm_pdf_buffer = io.BytesIO()
            # Convert to RGB for PDF compatibility
            rgb_img = Image.new("RGB", watermark_img.size, (255, 255, 255))
            rgb_img.paste(watermark_img, mask=watermark_img.split()[3])
            rgb_img.save(wm_pdf_buffer, format="PDF", resolution=144.0)
            wm_pdf_buffer.seek(0)

            # Overlay watermark
            wm_pdf = pikepdf.open(wm_pdf_buffer)
            if len(wm_pdf.pages) > 0:
                wm_page = wm_pdf.pages[0]
                # Use pikepdf's add_overlay to merge the watermark page onto this page
                page.add_overlay(wm_page)

            wm_pdf.close()

        output = io.BytesIO()
        pdf.save(output)
        pdf.close()
        return output.getvalue()

    def apply_image_watermark(
        self,
        image_bytes: bytes,
        text: str,
        opacity: float = 0.3,
        position: str = "diagonal",
    ) -> bytes:
        """Apply a text watermark to an image using Pillow."""
        from PIL import Image, ImageDraw, ImageFont

        # Open image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        width, height = img.size

        # Create watermark overlay
        overlay = Image.new("RGBA", (width, height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        # Use default font
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        except (OSError, IOError):
            font = ImageFont.load_default()

        alpha = int(opacity * 255)

        if position == "diagonal":
            # Draw text diagonally
            temp = Image.new("RGBA", (width * 2, height * 2), (255, 255, 255, 0))
            temp_draw = ImageDraw.Draw(temp)
            for y in range(0, height * 2, 150):
                for x in range(-width, width * 2, 350):
                    temp_draw.text((x, y), text, fill=(128, 128, 128, alpha), font=font)
            rotated = temp.rotate(-45, expand=False, center=(width, height))
            left = (rotated.width - width) // 2
            top_crop = (rotated.height - height) // 2
            overlay = rotated.crop((left, top_crop, left + width, top_crop + height))
        elif position == "center":
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (width - tw) // 2
            y = (height - th) // 2
            draw.text((x, y), text, fill=(128, 128, 128, alpha), font=font)
        elif position == "top":
            draw.text((20, 20), text, fill=(128, 128, 128, alpha), font=font)
        elif position == "bottom":
            bbox = draw.textbbox((0, 0), text, font=font)
            th = bbox[3] - bbox[1]
            draw.text((20, height - th - 20), text, fill=(128, 128, 128, alpha), font=font)

        # Composite
        result = Image.alpha_composite(img, overlay)
        result = result.convert("RGB")

        output = io.BytesIO()
        output_format = "PNG"
        result.save(output, format=output_format)
        return output.getvalue()

    def generate_css_watermark(
        self,
        text: str,
        opacity: float = 0.3,
        position: str = "diagonal",
    ) -> str:
        """Return CSS/HTML overlay div for watermarking in preview."""
        transform = ""
        pos_style = ""

        if position == "diagonal":
            transform = "transform: rotate(-45deg);"
            pos_style = "top: 50%; left: 50%; margin-top: -50px; margin-left: -100px;"
        elif position == "center":
            pos_style = "top: 50%; left: 50%; transform: translate(-50%, -50%);"
        elif position == "top":
            pos_style = "top: 20px; left: 20px;"
        elif position == "bottom":
            pos_style = "bottom: 20px; left: 20px;"

        return (
            f'<div style="position: fixed; {pos_style} {transform} '
            f'opacity: {opacity}; font-size: 48px; color: gray; '
            f'pointer-events: none; z-index: 9999; '
            f'white-space: nowrap;">{text}</div>'
        )
