"""Photo checks and pre-processing before storing or Gemini: real file type from the bytes,
then fix rotation, shrink, and re-encode as a fresh JPEG with no EXIF (so no GPS location)."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()  # lets Pillow open iPhone HEIC/HEIF photos

MAX_SIDE = 2048
JPEG_QUALITY = 88


NOT_AN_IMAGE = ("That file doesn't look like a photo we can read. Please upload a JPEG, PNG, "
                "WebP or HEIC image.")
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"heif"}


class ImageError(ValueError):
    """The upload is not an image we can read. The message is safe to show the owner."""


def sniff_image_type(data: bytes) -> str | None:
    """'jpeg' / 'png' / 'webp' / 'heic' from the file's first bytes, or None. The file name and
    the browser's content type are never trusted."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "heic"
    return None


def preprocess(data: bytes) -> bytes:
    """EXIF auto-rotate, long side <= 2048px, RGB JPEG. The output is a new image: EXIF (GPS,
    camera, time), XMP and ICC data are not copied into it."""
    if sniff_image_type(data) is None:
        raise ImageError(NOT_AN_IMAGE)
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
            img.info.clear()  # nothing from the original file's metadata goes into the copy
            img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageError(NOT_AN_IMAGE) from exc
