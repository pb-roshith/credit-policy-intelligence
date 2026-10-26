import logging
import io
from typing import Optional
from pydantic import BaseModel
from colorthief import ColorThief
import pypdf

logger = logging.getLogger(__name__)

class ThemeExtractionResponse(BaseModel):
    primary_color: str
    secondary_color: str
    theme_palette: list[str]

def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])

def extract_theme_from_document_bytes(file_bytes: bytes, filename: str) -> Optional[ThemeExtractionResponse]:
    """
    Extracts visual colors from an image or from images embedded on the first PDF page.

    pypdf does not render PDF pages, so vector-only PDF artwork cannot be sampled.
    """
    try:
        image_streams: list[io.BytesIO] = []

        if filename.lower().endswith(".pdf"):
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            if not reader.pages:
                return None

            # Process larger assets first because they are more likely to contain
            # the page's dominant branding than small icons or decorative images.
            embedded_images = sorted(
                reader.pages[0].images,
                key=lambda image: len(image.data),
                reverse=True,
            )
            image_streams = [io.BytesIO(image.data) for image in embedded_images]
            if not image_streams:
                logger.warning("No embedded images found on the first PDF page")
                return None
        else:
            image_streams = [io.BytesIO(file_bytes)]

        # Build a combined palette, keeping colors from larger PDF images first.
        palette_rgb: list[tuple[int, int, int]] = []
        for image_stream in image_streams:
            try:
                extracted = ColorThief(image_stream).get_palette(color_count=6, quality=1)
            except (OSError, ValueError):
                logger.debug("Skipping an embedded image that ColorThief cannot decode")
                continue
            for rgb in extracted:
                if rgb not in palette_rgb:
                    palette_rgb.append(rgb)

        if not palette_rgb:
            return None
        
        # Filter out near-white and near-black colors to find actual brand colors
        vibrant_colors = []
        for rgb in palette_rgb:
            r, g, b = rgb
            # Filter out whites/grays
            if r > 240 and g > 240 and b > 240:
                continue
            # Filter out black
            if r < 15 and g < 15 and b < 15:
                continue
            vibrant_colors.append(rgb_to_hex((r, g, b)))
            
        # If we didn't find enough colors, just use whatever was extracted
        if not vibrant_colors:
            vibrant_colors = [rgb_to_hex(rgb) for rgb in palette_rgb]
            
        # Pad palette up to 5 colors if necessary
        default_palette = ["#002060", "#800020", "#1e293b", "#3b82f6", "#f59e0b"]
        final_palette = vibrant_colors[:5]
        while len(final_palette) < 5:
            final_palette.append(default_palette[len(final_palette)])
            
        return ThemeExtractionResponse(
            primary_color=final_palette[0],
            secondary_color=final_palette[1],
            theme_palette=final_palette
        )
        
    except Exception as e:
        logger.error(f"Error during visual theme extraction: {e}")
        return None
