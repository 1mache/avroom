from __future__ import annotations

"""Application-wide settings helpers.

This module centralizes configuration such as the image storage directory so that
both the API layer and core logic can share the same behavior.
"""

import os
from pathlib import Path


IMAGE_STORAGE_DIR = ""
DEFAULT_IMAGE_STORAGE_SUBDIR = "tmp/images"
DEFAULT_3D_STORAGE_SUBDIR = "tmp/3d"

# One worker holds a full model stack in VRAM, so the ceiling is a guard
# against a typo in INFERENCE_WORKERS exhausting the GPU.
MAX_INFERENCE_WORKERS = 8
DEFAULT_INFERENCE_JOB_TIMEOUT_SEC = 600


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
    - If the `IMAGE_STORAGE_DIR` env var is set, that path is used (created if
      it doesn't exist yet — unlike the old behavior, a not-yet-existing
      configured path is no longer silently ignored).
    - Otherwise, a local `tmp/images/` directory in project root is used.

    Only meaningful when :func:`get_storage_backend` is ``"local"``; under the
    ``"s3"`` backend this still backs :func:`get_scratch_dir`'s sibling
    sidecar-free layout for any local-only callers, but blob storage itself
    goes through ``core/storage``.
    """

    project_root = _project_root()
    configured_dir = os.environ.get("IMAGE_STORAGE_DIR", IMAGE_STORAGE_DIR).strip()
    if configured_dir:
        configured_path = Path(configured_dir).expanduser()
        if not configured_path.is_absolute():
            configured_path = project_root / configured_path
        return configured_path

    return project_root / DEFAULT_IMAGE_STORAGE_SUBDIR


def get_3d_storage_dir() -> Path:
    """Resolve the directory used to persist generated GLB models on disk.

    Overridable via the `THREED_STORAGE_DIR` env var (relative paths are
    resolved against the project root), mirroring :func:`get_image_storage_dir`.
    """
    configured_dir = os.environ.get("THREED_STORAGE_DIR", "").strip()
    if configured_dir:
        configured_path = Path(configured_dir).expanduser()
        if not configured_path.is_absolute():
            configured_path = _project_root() / configured_path
        return configured_path

    return _project_root() / DEFAULT_3D_STORAGE_SUBDIR


def get_scratch_dir() -> Path:
    """Resolve the directory for ephemeral, node-local caches.

    Mask candidates, the depth-map cache, and the camera-calibration cache are
    all recomputable and hot; they always live on local disk here regardless
    of `STORAGE_BACKEND`, so the API process and its inference workers must
    share one host (see docs/backend/concurrency.md). Overridable via
    `SCRATCH_DIR`; defaults to the same directory as
    :func:`get_image_storage_dir` so existing local-mode behavior is
    unchanged.
    """
    configured_dir = os.environ.get("SCRATCH_DIR", "").strip()
    if configured_dir:
        configured_path = Path(configured_dir).expanduser()
        if not configured_path.is_absolute():
            configured_path = _project_root() / configured_path
        return configured_path

    return get_image_storage_dir()


def get_inference_worker_count() -> int:
    """Return configured inference worker subprocess count.

    ``INFERENCE_WORKERS=0`` (default) keeps inline execution with the existing
    process-wide inference lock. Values above zero spawn that many GPU worker
    subprocesses (~one full model stack per worker in VRAM).
    """
    return max(0, min(_env_int("INFERENCE_WORKERS", 0), MAX_INFERENCE_WORKERS))


def get_inference_job_timeout_sec() -> int:
    """Maximum seconds the API waits for one inference worker job to finish."""
    return max(1, _env_int("INFERENCE_JOB_TIMEOUT_SEC", DEFAULT_INFERENCE_JOB_TIMEOUT_SEC))


def get_upload_validation_enabled() -> bool:
    """Return whether upload technical + content validation runs (default: enabled)."""
    return _env_bool("VALIDATE", True)


def get_camera_calibration_enabled() -> bool:
    """Return whether upload-time GeoCalib calibration runs (default: enabled)."""
    return _env_bool("CAMERA_CALIB", True)


def get_debug_endpoints_enabled() -> bool:
    """Return whether the ``/debug`` visualization endpoints are exposed (default: enabled)."""
    return _env_bool("DEBUG_ENDPOINTS", True)


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


# --- AWS deployment prep: storage backend, database, auth, CORS -----------
#
# Everything below stays behind an env-driven switch so the app runs exactly
# as before with no env vars set. See docs/deployment/aws-runbook.md.


def get_storage_backend() -> str:
    """Return which `core.storage.ObjectStore` backs durable blobs.

    ``"local"`` (default) keeps writing under :func:`get_image_storage_dir` /
    :func:`get_3d_storage_dir`, unchanged from today. ``"s3"`` routes the same
    keys through an S3 bucket instead. Any other value falls back to
    ``"local"`` rather than failing startup.
    """
    raw = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
    return raw if raw in {"local", "s3"} else "local"


def get_s3_bucket() -> str:
    """Return the S3 bucket name for durable blobs (`STORAGE_BACKEND=s3` only)."""
    return os.environ.get("S3_BUCKET", "").strip()


def get_s3_prefix() -> str:
    """Return the key prefix under which all blobs are stored in the bucket."""
    return os.environ.get("S3_PREFIX", "avroom").strip().strip("/")


def get_s3_region() -> str:
    """Return the AWS region for the S3 client (boto3 falls back to its own
    default resolution — env/credentials file/instance profile — if empty)."""
    return os.environ.get("S3_REGION", "").strip()


def get_auth_mode() -> str:
    """Return the auth mode: ``"single_user"`` (default, local dev) or ``"jwt"``.

    In ``single_user`` mode every request is treated as one fixed,
    auto-provisioned local user — no login, no token, identical UX to today.
    In ``jwt`` mode requests must carry a valid ``Authorization: Bearer``
    token. Any other value falls back to ``"single_user"``, so a typo'd env
    var degrades to local-dev behavior rather than an unrecognized mode.
    """
    raw = os.environ.get("AUTH_MODE", "single_user").strip().lower()
    return raw if raw in {"single_user", "jwt"} else "single_user"


def get_database_url() -> str:
    """Return the SQLAlchemy database URL.

    Defaults to the docker-compose Postgres service so `docker compose up db`
    plus an unmodified `.env` is enough to run locally with real persistence.
    Host port 5433 (not 5432): a native Postgres install may already own 5432
    on the host, and `docker-compose.yml` maps the container's 5432 there to
    avoid the conflict.
    """
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://avroom:avroom@localhost:5433/avroom",
    ).strip()


def get_jwt_secret() -> str:
    """Return the JWT signing secret.

    No safe default exists for this one: an empty/default secret would let
    anyone forge tokens. Callers in `jwt` auth mode must fail loudly if this
    is unset, rather than silently signing with a well-known string.
    """
    return os.environ.get("JWT_SECRET", "").strip()


def get_jwt_expire_minutes() -> int:
    """Return how long an issued JWT stays valid, in minutes."""
    return max(1, _env_int("JWT_EXPIRE_MINUTES", 60 * 24 * 7))


def get_cors_allow_origins() -> list[str]:
    """Return the list of origins the API accepts CORS requests from.

    Comma-separated via `CORS_ALLOW_ORIGINS`; defaults to the two local Vite
    dev origins so local dev needs no env var, matching today's hardcoded
    `main.py` list.
    """
    raw = os.environ.get(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_debug_image_save() -> bool:
    """Return whether the AI pipeline's per-stage debug image dumps are written.

    `TestModules`' `DebugImageSaver` writes dozens of PNGs per `/segment` call
    to a fixed local directory (`TestModules/outputs/`) that nothing ever
    reads back. Default on (matches today's behavior everywhere); set to
    `false` in containers, where that directory is pure waste.
    """
    return _env_bool("DEBUG_IMAGE_SAVE", True)

