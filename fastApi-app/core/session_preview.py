from __future__ import annotations

"""Dashboard thumbnail generation.

The frontend recomposes and posts a fresh thumbnail after every edit, but a
session needs a preview from the moment it's created too — otherwise a
just-uploaded, never-edited session shows an empty placeholder card. This
module writes that first thumbnail (a downscaled copy of the original upload)
at upload time; the frontend's own composited preview overwrites it on the
first edit.
"""

import io
import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from core.object_storage import session_preview_path

logger = logging.getLogger(__name__)

# Long edge of the stored thumbnail, matching the frontend's PREVIEW_MAX_WIDTH
# (react-front/src/utils/preview.ts) so upload-time and edit-time thumbnails
# are visually consistent in size.
PREVIEW_MAX_WIDTH = 640
PREVIEW_QUALITY = 82


def write_upload_preview(storage_dir: Path, uid: str, image_bytes: bytes) -> None:
    """Write a downscaled JPEG thumbnail for a freshly uploaded session.

    Best-effort: any failure is logged and swallowed so a thumbnail problem
    never fails the upload it's attached to. Uploads may be RGBA PNG, which
    JPEG can't hold, so the image is flattened onto a white background first.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.load()
            if img.mode != "RGB":
                flattened = Image.new("RGB", img.size, (255, 255, 255))
                flattened.paste(img, mask=img.getchannel("A") if "A" in img.getbands() else None)
                img = flattened

            scale = min(1.0, PREVIEW_MAX_WIDTH / img.width)
            if scale < 1.0:
                size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
                img = img.resize(size, Image.LANCZOS)

            path = session_preview_path(storage_dir, uid)
            img.save(path, format="JPEG", quality=PREVIEW_QUALITY)
            logger.info(
                "Upload preview written: uid=%s path=%s size=%dx%d",
                uid,
                path,
                img.width,
                img.height,
            )
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.warning(
            "Upload preview generation failed (non-fatal): uid=%s detail=%s",
            uid,
            exc,
        )
