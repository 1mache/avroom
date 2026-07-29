from __future__ import annotations

"""Application-wide settings helpers.

This module centralizes configuration such as the image storage directory so that
both the API layer and core logic can share the same behavior.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


IMAGE_STORAGE_DIR = ""
DEFAULT_IMAGE_STORAGE_SUBDIR = "tmp/images"
DEFAULT_3D_STORAGE_SUBDIR = "tmp/3d"


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


def get_3d_storage_dir() -> Path:
    """Resolve the directory used to persist generated GLB models on disk."""
    return _project_root() / DEFAULT_3D_STORAGE_SUBDIR


def get_sessions_file() -> Path:
    """Return path to tmp/sessions.json, one level above the image storage dir."""
    return get_image_storage_dir().parent / "sessions.json"


def get_names_file() -> Path:
    """Return path to tmp/names.json, a uid->name mapping sibling of sessions.json."""
    return get_image_storage_dir().parent / "names.json"


def get_session_timestamps_file() -> Path:
    """Return path to tmp/session_timestamps.json, sibling of sessions.json."""
    return get_image_storage_dir().parent / "session_timestamps.json"


def load_names() -> dict[str, str]:
    """Load the uid->name mapping from names.json.

    Returns an empty dict if the file is absent or malformed so callers never
    have to handle missing-names specially.
    """
    import json

    names_file = get_names_file()
    if not names_file.exists():
        return {}
    try:
        data = json.loads(names_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}
    except (json.JSONDecodeError, ValueError):
        return {}


def set_session_name(uid: str, name: str) -> None:
    """Persist a human-readable name for a session uid.

    Names are unique across sessions.  If `name` is already assigned to a
    *different* uid, raises ValueError so the caller can surface a 409 to the
    client without knowing the storage details.
    """
    import json

    names = load_names()

    existing_uid = next((k for k, v in names.items() if v == name), None)
    if existing_uid is not None and existing_uid != uid:
        raise ValueError(f"Name '{name}' is already used by another session.")

    names[uid] = name

    names_file = get_names_file()
    names_file.parent.mkdir(parents=True, exist_ok=True)
    names_file.write_text(json.dumps(names, indent=2), encoding="utf-8")


def deregister_uid(uid: str) -> None:
    """Remove uid from sessions.json. No-op if uid is not present."""
    import json

    sessions_file = get_sessions_file()
    if not sessions_file.exists():
        return

    try:
        uids: list[str] = json.loads(sessions_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return

    filtered = [u for u in uids if u != uid]
    if len(filtered) == len(uids):
        return

    sessions_file.write_text(json.dumps(filtered, indent=2), encoding="utf-8")


def remove_session_name(uid: str) -> None:
    """Remove uid's name entry from names.json. No-op if uid has no name."""
    import json

    names = load_names()
    if names.pop(uid, None) is None:
        return

    names_file = get_names_file()
    names_file.parent.mkdir(parents=True, exist_ok=True)
    names_file.write_text(json.dumps(names, indent=2), encoding="utf-8")


def _load_session_timestamps() -> dict[str, str]:
    """Load uid->last_changed ISO timestamps from session_timestamps.json."""
    timestamps_file = get_session_timestamps_file()
    if not timestamps_file.exists():
        return {}
    try:
        data = json.loads(timestamps_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}
    except (json.JSONDecodeError, ValueError):
        return {}


def _save_session_timestamps(timestamps: dict[str, str]) -> None:
    """Persist the uid->last_changed mapping to session_timestamps.json."""
    timestamps_file = get_session_timestamps_file()
    timestamps_file.parent.mkdir(parents=True, exist_ok=True)
    timestamps_file.write_text(json.dumps(timestamps, indent=2), encoding="utf-8")


def touch_session(uid: str) -> str:
    """Record a fresh last-changed timestamp for one session and return it."""
    timestamps = _load_session_timestamps()
    now = datetime.now(UTC).isoformat()
    timestamps[uid] = now
    _save_session_timestamps(timestamps)
    return now


def get_session_last_changed(uid: str) -> str | None:
    """Return the persisted last-changed timestamp for a session, if any."""
    return _load_session_timestamps().get(uid)


def clear_session_last_changed(uid: str) -> None:
    """Remove one session's last-changed entry. No-op when absent."""
    timestamps = _load_session_timestamps()
    if timestamps.pop(uid, None) is None:
        return
    _save_session_timestamps(timestamps)


def is_session_registered(uid: str) -> bool:
    """Return whether ``uid`` appears in sessions.json."""
    sessions_file = get_sessions_file()
    if not sessions_file.exists():
        return False
    try:
        uids: list[str] = json.loads(sessions_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return False
    return uid in uids


class SessionNotFoundError(LookupError):
    """Raised when a sync-check targets a uid absent from sessions.json."""


def evaluate_session_sync(uid: str, client_last_changed: str | None) -> tuple[str, bool]:
    """Compare client and server session timestamps.

    Returns:
        Tuple of ``(server_last_changed, needs_refresh)``. ``server_last_changed``
        is an empty string when the session exists but has no recorded timestamp.
    """
    if not is_session_registered(uid):
        raise SessionNotFoundError(uid)
    server_last_changed = get_session_last_changed(uid) or ""
    needs_refresh = client_last_changed != server_last_changed
    return server_last_changed, needs_refresh


def register_uid(uid: str) -> None:
    """Append uid to sessions.json, creating the file if absent."""

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


def get_inference_worker_count() -> int:
    """Return configured inference worker subprocess count.

    ``INFERENCE_WORKERS=0`` (default) keeps inline execution with the existing
    process-wide inference lock. Values above zero spawn that many GPU worker
    subprocesses (~one full model stack per worker in VRAM).
    """
    raw = os.environ.get("INFERENCE_WORKERS", "0").strip()
    try:
        count = int(raw)
    except ValueError:
        count = 0
    return max(0, min(count, 8))


def get_inference_job_timeout_sec() -> int:
    """Maximum seconds the API waits for one inference worker job to finish."""
    raw = os.environ.get("INFERENCE_JOB_TIMEOUT_SEC", "600").strip()
    try:
        timeout = int(raw)
    except ValueError:
        timeout = 600
    return max(1, timeout)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def get_upload_validation_enabled() -> bool:
    """Return whether upload technical + content validation runs (default: enabled)."""
    return _env_bool("VALIDATE", True)


def get_upload_min_bytes() -> int:
    return max(1, _env_int("UPLOAD_MIN_BYTES", 1024))


def get_upload_max_bytes() -> int:
    return max(get_upload_min_bytes(), _env_int("UPLOAD_MAX_BYTES", 25 * 1024 * 1024))


def get_upload_min_width() -> int:
    return max(1, _env_int("UPLOAD_MIN_WIDTH", 640))


def get_upload_min_height() -> int:
    return max(1, _env_int("UPLOAD_MIN_HEIGHT", 480))


def get_upload_max_width() -> int:
    return max(get_upload_min_width(), _env_int("UPLOAD_MAX_WIDTH", 8192))


def get_upload_max_height() -> int:
    return max(get_upload_min_height(), _env_int("UPLOAD_MAX_HEIGHT", 8192))


def get_upload_max_megapixels() -> float:
    return max(0.1, _env_float("UPLOAD_MAX_MEGAPIXELS", 24.0))


def get_upload_max_aspect_ratio() -> float:
    return max(1.0, _env_float("UPLOAD_MAX_ASPECT_RATIO", 3.5))


def get_upload_blur_min_variance() -> float:
    return max(0.0, _env_float("UPLOAD_BLUR_MIN_VARIANCE", 50.0))


def get_upload_exposure_mean_min() -> float:
    return max(0.0, _env_float("UPLOAD_EXPOSURE_MEAN_MIN", 20.0))


def get_upload_exposure_mean_max() -> float:
    return min(255.0, _env_float("UPLOAD_EXPOSURE_MEAN_MAX", 235.0))


def get_upload_clip_fraction_max() -> float:
    return min(1.0, max(0.0, _env_float("UPLOAD_CLIP_FRACTION_MAX", 0.85)))


def get_upload_min_spatial_variance() -> float:
    return max(0.0, _env_float("UPLOAD_MIN_SPATIAL_VARIANCE", 100.0))


def get_upload_min_alpha_opaque_ratio() -> float:
    return min(1.0, max(0.0, _env_float("UPLOAD_MIN_ALPHA_OPAQUE_RATIO", 0.05)))


def get_upload_allowed_mime_types() -> frozenset[str]:
    raw = os.environ.get(
        "UPLOAD_ALLOWED_MIME_TYPES",
        "image/jpeg,image/png,image/webp",
    )
    values = {part.strip() for part in raw.split(",") if part.strip()}
    return frozenset(values or {"image/jpeg", "image/png", "image/webp"})

