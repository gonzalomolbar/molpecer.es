"""Re-encode anything a visitor uploads into clean WebP files. Bump PIPELINE_VERSION when the output changes."""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:  # local tests without the wheel
    pass

PIPELINE_VERSION = 1
FULL_PX = 1600
THUMB_PX = 400
MAX_PIXELS = 40_000_000
ALLOWED = {"JPEG", "PNG", "WEBP", "GIF", "HEIF", "MPO"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class BadImage(ValueError):
    pass


def reencode(data, full_px=FULL_PX, thumb_px=THUMB_PX):
    """Returns (full_webp_bytes, thumb_webp_bytes, (w, h)) or raises BadImage."""
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").upper()
        if fmt not in ALLOWED:
            raise BadImage(f"format {fmt or 'unknown'}")
        w, h = img.size
        if w * h > MAX_PIXELS or w < 8 or h < 8:
            raise BadImage(f"size {w}x{h}")
        if getattr(img, "n_frames", 1) > 1:
            img.seek(0)
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        raise BadImage(str(e)) from e
    full = _fit(img, full_px)
    thumb = _fit(img, thumb_px)
    return _webp(full, 82), _webp(thumb, 75), full.size


def _fit(img, px):
    out = img.copy()
    out.thumbnail((px, px), Image.Resampling.LANCZOS)
    return out


def _webp(img, quality):
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=quality, method=4)  # no metadata is carried over
    return buf.getvalue()
