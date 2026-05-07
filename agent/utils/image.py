"""Image-handling helpers shared across the harness.

The Anthropic API has a per-image dimension cap when a single request
contains more than one image (the "many-image" rule): every image must
be <= 2000 px on both sides. Browser screenshots in `full_page` mode
and arbitrary images fetched from URLs (Linear/Slack/GitHub) routinely
exceed this on height, so we downscale before encoding to base64.
"""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

MAX_IMAGE_DIM = 2000  # Anthropic many-image limit (px on either side)
_PNG_MIME = "image/png"


def downscale_image_bytes(
    image_bytes: bytes,
    mime_type: str,
    max_dim: int = MAX_IMAGE_DIM,
) -> tuple[bytes, str, tuple[int, int] | None, tuple[int, int] | None]:
    """If `image_bytes` exceeds `max_dim` on either side, return a resized PNG.

    Returns:
        (bytes_for_model, mime_type_for_model, original_dims, new_dims).
        - `original_dims` is the (w, h) of the input, or None if Pillow
          is unavailable.
        - `new_dims` is the (w, h) of the resized image, or None if no
          resize was performed (input was already small enough).
        - When a resize happens, `mime_type_for_model` is always
          `image/png` regardless of input format — Pillow re-encodes
          uniformly. Caller-supplied bytes pass through unchanged when
          no resize is needed (preserves animated GIFs, EXIF, etc.).
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow unavailable; cannot downscale image")
        return image_bytes, mime_type, None, None

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            w, h = img.size
            if w <= max_dim and h <= max_dim:
                return image_bytes, mime_type, (w, h), None
            scale = max_dim / max(w, h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            resized = img.convert("RGBA").resize((new_w, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            resized.save(buf, format="PNG", optimize=True)
            return buf.getvalue(), _PNG_MIME, (w, h), (new_w, new_h)
    except Exception:  # noqa: BLE001 — Pillow surfaces many decode errors
        logger.exception("Could not decode/resize image (%s, %d bytes)", mime_type, len(image_bytes))
        return image_bytes, mime_type, None, None
