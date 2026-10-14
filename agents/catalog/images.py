"""Photo pre-processing before Gemini: fix rotation, shrink, convert to JPEG."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()  # lets Pillow open iPhone HEIC/HEIF photos

MAX_SIDE = 2048
JPEG_QUALITY = 88


class ImageError(ValueError):
    """The upload is not an image we can read. The message is safe to show the owner."""


def preprocess(data: bytes) -> bytes:
    """EXIF auto-rotate, long side <= 2048px, RGB JPEG."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode in ("RGBA", "LA", "P"):
                # Flatten transparency onto white so PNG menus don't turn black.
                rgba = img.convert("RGBA")
                img = Image.new("RGB", rgba.size, (255, 255, 255))
                img.paste(rgba, mask=rgba.getchannel("A"))
            else:
                img = img.convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageError(
            "That file doesn't look like a photo we can read. Please upload a JPEG, PNG, "
            "WebP or HEIC image."
        ) from exc
