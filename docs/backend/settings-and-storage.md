# Settings and Image Storage

All settings live in [`fastApi-app/settings.py`](../../fastApi-app/settings.py). There is no `.env` parsing or `pydantic-settings` configuration in the app today — the file is plain Python with module-level constants.

## Module — [`fastApi-app/settings.py`](../../fastApi-app/settings.py)

```9:43:fastApi-app/settings.py
from pathlib import Path


IMAGE_STORAGE_DIR = ""
DEFAULT_IMAGE_STORAGE_SUBDIR = "images"


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
    - Otherwise, a local `images/` directory in project root is used.
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
```

## Storage directory resolution

`get_image_storage_dir()` returns the first match:

1. If module constant `IMAGE_STORAGE_DIR` is set to a non-empty string AND the resulting path **exists**, use it. Relative paths are resolved against the "project root" (closest ancestor containing a `pyproject.toml`).
2. Otherwise, return `<project_root>/images`.

Because the deepest `pyproject.toml` walking up from `settings.py` is [`fastApi-app/pyproject.toml`](../../fastApi-app/pyproject.toml), the **default storage dir is `fastApi-app/images/`**.

> Caveat: a configured `IMAGE_STORAGE_DIR` is silently ignored if the path doesn't exist. There's no warning logged. If your override isn't picking up, check that the directory is created first.

## Storage layout at runtime

```
fastApi-app/images/
├── {image_id}.{ext}             - one per upload (jpg/png/...)
└── tmp/
    └── {image_id}_debug.png     - click-marker overlay
```

- `{image_id}.{ext}` is written by `upload_image` — the suffix comes from the original filename or defaults to `.png` ([`api/routes.py`](../../fastApi-app/api/routes.py) lines 41–48).
- `tmp/{image_id}_debug.png` is written by `_create_debug_click_image` on every click ([`core/image_processing.py`](../../fastApi-app/core/image_processing.py) lines 32–50).

Neither file is ever cleaned up by the service.

## What's not configurable

- CORS origins (hardcoded in [`fastApi-app/main.py`](../../fastApi-app/main.py) lines 16–22).
- Output format (hardcoded `"png"` in `segment_at_click`).
- Debug overlay subdir name (`"tmp"` constant inside `_create_debug_click_image`).
- Mask dilation radius, SD strength, depth model IDs — all live in the AI pipeline; see [ai-pipeline/](../ai-pipeline/README.md).

## Environment variables read elsewhere

These don't live in `settings.py`, but the AI pipeline reads them at runtime:

- `SAM_CHECKPOINT_PATH` — explicit path to the SAM ViT-B checkpoint.
- `SAM_AUTO_DOWNLOAD` — set to `0`/`false`/`no` to disable the download fallback.
- `SAM_CHECKPOINT_URL` — override the default `dl.fbaipublicfiles.com` URL.

Source: [`SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) lines 30–55.
