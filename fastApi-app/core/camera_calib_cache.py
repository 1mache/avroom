from __future__ import annotations

"""Filesystem cache for per-session camera calibration JSON."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def camera_calib_path(base_dir: Path, session_id: str) -> Path:
    """Return canonical path for one session's camera calibration cache."""
    return base_dir / f"{session_id}_camera_calib.json"


def save_camera_calib(base_dir: Path, session_id: str, payload: dict[str, Any]) -> Path:
    """Persist calibration fields as JSON and return the written path."""
    path = camera_calib_path(base_dir, session_id)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info(
        "Camera calib cache saved: session_id=%s path=%s pitch=%.2f fx=%.1f",
        session_id,
        path,
        float(payload.get("pitch_deg", 0.0)),
        float(payload.get("fx", 0.0)),
    )
    return path


def load_camera_calib(base_dir: Path, session_id: str) -> dict[str, Any] | None:
    """Load cached calibration for a session, or ``None`` when absent."""
    path = camera_calib_path(base_dir, session_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            logger.warning("Malformed camera calib cache: %s", path)
            return None
        logger.debug("Camera calib cache hit: session_id=%s path=%s", session_id, path)
        return raw
    except json.JSONDecodeError:
        logger.warning("Malformed camera calib cache: %s", path)
        return None


def delete_session_camera_calib(base_dir: Path, session_id: str) -> int:
    """Remove the session calibration cache file if present."""
    path = camera_calib_path(base_dir, session_id)
    if not path.exists():
        return 0
    path.unlink(missing_ok=True)
    logger.debug("Deleted camera calib cache: session_id=%s", session_id)
    return 1
