# Settings and Image Storage

All settings live in [`fastApi-app/settings.py`](../../fastApi-app/settings.py). There is no `.env` parsing or `pydantic-settings` configuration in the app today — the file is plain Python with module-level constants.

## Module — [`fastApi-app/settings.py`](../../fastApi-app/settings.py)

```9:43:fastApi-app/settings.py
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
```

## Storage directory resolution

`get_image_storage_dir()` returns the first match:

1. If module constant `IMAGE_STORAGE_DIR` is set to a non-empty string AND the resulting path **exists**, use it. Relative paths are resolved against the "project root" (closest ancestor containing a `pyproject.toml`).
2. Otherwise, return `<project_root>/tmp/images`.

Because the deepest `pyproject.toml` walking up from `settings.py` is [`fastApi-app/pyproject.toml`](../../fastApi-app/pyproject.toml), the **default storage dir is `fastApi-app/tmp/images/`**.

> Caveat: a configured `IMAGE_STORAGE_DIR` is silently ignored if the path doesn't exist. There's no warning logged. If your override isn't picking up, check that the directory is created first.

## Sessions file

`get_sessions_file()` ([`settings.py`](../../fastApi-app/settings.py) lines 52–54) returns:

```
<image_storage_dir>/../sessions.json   →   fastApi-app/tmp/sessions.json
```

`register_uid(uid)` ([`settings.py`](../../fastApi-app/settings.py) lines 104–121) appends a UID string to that file. The file contains a plain JSON array of UUID strings:

```json
["f5e0edc4-fe7a-48bf-bd76-d706d32b61c1", "a1b2c3d4-..."]
```

Every `POST /images/upload` calls `register_uid` after writing the image. `GET /images/sessions` reads the array, enriches each uid with its name from `names.json`, and returns `list[SessionInfo]`. The file is created on first write; if it doesn't exist yet, `GET /images/sessions` returns `[]`.

## Names file

`get_names_file()` ([`settings.py`](../../fastApi-app/settings.py) lines 57–59) returns:

```
<image_storage_dir>/../names.json   →   fastApi-app/tmp/names.json
```

The file is a JSON object mapping uid strings to human-readable names:

```json
{
  "f5e0edc4-fe7a-48bf-bd76-d706d32b61c1": "living room before",
  "a1b2c3d4-...": "kitchen test"
}
```

`load_names()` ([`settings.py`](../../fastApi-app/settings.py) lines 62–79) reads this file and returns a `dict[str, str]`. Returns `{}` if file absent or malformed — callers never need to handle a missing-file case.

`set_session_name(uid, name)` ([`settings.py`](../../fastApi-app/settings.py) lines 82–101) writes a new entry. Raises `ValueError` if `name` is already assigned to a *different* uid (uniqueness enforced here, not at the HTTP layer). Called by `POST /images/{uid}/name`.

## 3D model storage

`get_3d_storage_dir()` ([`settings.py`](../../fastApi-app/settings.py) lines 47–49) returns `<project_root>/tmp/3d`. Generated GLB files are stored as `{uid}.glb` and served by `GET /objects/{uid}`.

## Storage layout at runtime

```
fastApi-app/tmp/
├── sessions.json                    - array of all registered UIDs
├── names.json                       - uid → human-readable name map
├── images/
│   ├── {image_id}.{ext}             - one per upload (jpg/png/...)
│   ├── {image_id}_background.png    - background result (written on inpaint)
│   ├── {image_id}_cutout.png        - cutout result (written on inpaint)
│   ├── {image_id}_mask_{n}_refined.npy   - candidate refined mask (segmentation)
│   ├── {image_id}_mask_{n}_cutout.png    - candidate cutout preview (segmentation)
│   └── point/
│       └── {image_id}_debug.png     - click-marker overlay
└── 3d/
    └── {image_id}.glb               - 3D model (written by /objects/test-3d)
```

- `{image_id}.{ext}` is written by `upload_image` — the suffix comes from the original filename or defaults to `.png` ([`api/routes.py`](../../fastApi-app/api/routes.py) lines 41–48).
- `{image_id}_background.png` and `{image_id}_cutout.png` are written by `handle_click` on every click ([`api/routes.py`](../../fastApi-app/api/routes.py) lines 110–114).
- `point/{image_id}_debug.png` is written by `_create_debug_click_image` on every click ([`core/image_processing.py`](../../fastApi-app/core/image_processing.py) lines 33–51).
- `{image_id}.glb` is written by `generate_test_3d` ([`api/objects.py`](../../fastApi-app/api/objects.py) lines 43–103).

No file is ever cleaned up by the service.

## What's not configurable

- CORS origins (hardcoded in [`fastApi-app/main.py`](../../fastApi-app/main.py) lines 16–22).
- Output format (hardcoded `"png"` in `segment_at_click`).
- Debug overlay subdir name (`"point"` constant inside `_create_debug_click_image`).
- Mask dilation radius, SD strength, depth model IDs — all live in the AI pipeline; see [ai-pipeline/](../ai-pipeline/README.md).

## Environment variables read elsewhere

These don't live in `settings.py`, but the AI pipeline reads them at runtime:

- `SAM_CHECKPOINT_PATH` — explicit path to the SAM ViT-B checkpoint.
- `SAM_AUTO_DOWNLOAD` — set to `0`/`false`/`no` to disable the download fallback.
- `SAM_CHECKPOINT_URL` — override the default `dl.fbaipublicfiles.com` URL.

Source: [`sam_segmentation_strategy.py`](../../TestModules/src/ai_engines/segmentation/strategies/sam_segmentation_strategy.py) lines 29–62.
