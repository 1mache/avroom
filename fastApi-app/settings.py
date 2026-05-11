from __future__ import annotations

"""Application-wide settings helpers.

This module centralizes configuration such as the image storage directory so that
both the API layer and core logic can share the same behavior.
"""

from pathlib import Path


IMAGE_STORAGE_DIR = ""
DEFAULT_IMAGE_STORAGE_SUBDIR = "tmp/images"


def _project_root() -> Path:
    """Return project root by locating the closest parent with pyproject.toml."""

    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return current


def get_image_storage_dir() -> Path:
    """Resolve the directory used to persist uploaded images on disk.

    The directory is determined as follows:
    - If `IMAGE_STORAGE_DIR` is set here and path exists, that path is used.
    - Otherwise, a local `tmp/images/` directory in project root is used.
    """

    project_root = _project_root()
    configured_dir = IMAGE_STORAGE_DIR.strip()
    if configured_dir:
        configured_path = Path(configured_dir).expanduser()
        if not configured_path.is_absolute():
            configured_path = project_root / configured_path
        if configured_path.exists():
            return configured_path

    return project_root / DEFAULT_IMAGE_STORAGE_SUBDIR


def get_sessions_file() -> Path:
    """Return path to tmp/sessions.json, one level above the image storage dir."""
    return get_image_storage_dir().parent / "sessions.json"


def register_uid(uid: str) -> None:
    """Append uid to sessions.json, creating the file if absent."""
    import json

    sessions_file = get_sessions_file()
    sessions_file.parent.mkdir(parents=True, exist_ok=True)

    uids: list[str] = []
    if sessions_file.exists():
        try:
            uids = json.loads(sessions_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            uids = []

    if uid not in uids:
        uids.append(uid)

    sessions_file.write_text(json.dumps(uids, indent=2), encoding="utf-8")

