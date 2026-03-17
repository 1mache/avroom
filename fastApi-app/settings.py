from __future__ import annotations

"""Application-wide settings helpers.

This module centralizes configuration such as the image storage directory so that
both the API layer and core logic can share the same behavior.
"""

import os
from pathlib import Path


IMAGE_STORAGE_ENV_VAR = "IMAGE_STORAGE_DIR"
DEFAULT_IMAGE_STORAGE_SUBDIR = "images"


def get_image_storage_dir() -> Path:
    """Resolve the directory used to persist uploaded images on disk.

    The directory is determined as follows:
    - If the `IMAGE_STORAGE_DIR` environment variable is set, its value is used.
    - Otherwise, a local `images/` directory next to this file is used.
    """

    env_value = os.getenv(IMAGE_STORAGE_ENV_VAR)
    if env_value:
        base_path = Path(env_value)
    else:
        base_path = Path(__file__).resolve().parent / DEFAULT_IMAGE_STORAGE_SUBDIR

    return base_path

