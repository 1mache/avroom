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

`get_3d_storage_dir()` ([`settings.py`](../../fastApi-app/settings.py) lines 47–49) returns `<project_root>/tmp/3d`. Generated GLB files are stored as `{uid}_{object_id}.glb` per object and served by `GET /3d/{uid}/{object_id}`. The legacy path `{uid}.glb` (sessions created before per-object numbering) is served by `GET /3d/{uid}` as an id-0 fallback.

## Storage layout at runtime

```
fastApi-app/tmp/
├── sessions.json                    - array of all registered UIDs
├── names.json                       - uid → human-readable name map
├── images/
│   ├── {image_id}.{ext}             - one per upload (jpg/png/...)
│   ├── {image_id}_background.png         - cumulative inpainted canvas (overwrites each inpaint)
│   ├── {image_id}_{object_id}_cutout.png - per-object cutout (numbered, never overwritten)
│   ├── {image_id}_cutout.png             - legacy flat cutout (sessions before per-object numbering)
│   ├── {image_id}_mask_{n}_refined.npy   - candidate refined mask (segmentation, temporary)
│   ├── {image_id}_mask_{n}_cutout.png    - candidate cutout preview (segmentation, temporary)
│   └── point/
│       └── {image_id}_debug.png          - click-marker overlay
└── 3d/
    ├── {image_id}_{object_id}.glb        - per-object 3D model (written by POST /3d/test-3d)
    └── {image_id}.glb                    - legacy flat 3D model (sessions before per-object numbering)
```

- `{image_id}.{ext}` is written by `upload_image` — the suffix comes from the original filename or defaults to `.png` ([`api/routes.py`](../../fastApi-app/api/routes.py) lines 41–48).
- `{image_id}_background.png` is written (and overwritten) by `inpaint_mask` on every successful inpaint, becoming the progressive canvas for the next object.
- `{image_id}_{object_id}_cutout.png` is written by `inpaint_mask` with a sequentially allocated `object_id` — prior objects are never overwritten. Path construction lives in [`core/object_storage.py`](../../fastApi-app/core/object_storage.py) (`object_cutout_path`, `next_object_id`).
- `point/{image_id}_debug.png` is written by `_create_debug_click_image` on every click ([`core/image_processing.py`](../../fastApi-app/core/image_processing.py) lines 64–82).
- `{image_id}_{object_id}.glb` is written by `generate_test_3d` ([`api/model_3d.py`](../../fastApi-app/api/model_3d.py) lines 49–126).

No file is ever cleaned up by the service automatically. `DELETE /images/{uid}` removes all artifacts for a session on explicit request.

## Artifact naming — `core/object_storage.py`

All `{uid}_{object_id}_…` filename construction is centralised in [`fastApi-app/core/object_storage.py`](../../fastApi-app/core/object_storage.py). Never construct these strings by hand in other modules.

Key helpers:

| Helper | Returns |
|---|---|
| `object_cutout_path(base_dir, uid, object_id)` | `{uid}_{object_id}_cutout.png` |
| `resolve_object_cutout_path(base_dir, uid, object_id)` | numbered path; for id 0, falls back to legacy `{uid}_cutout.png` if absent |
| `object_glb_path(glb_dir, uid, object_id)` | `{uid}_{object_id}.glb` |
| `resolve_object_glb_path(glb_dir, uid, object_id)` | numbered path; for id 0, falls back to legacy `{uid}.glb` if absent |
| `list_object_ids(base_dir, uid)` | sorted list of all object ids found on disk |
| `next_object_id(base_dir, uid)` | `max(list_object_ids) + 1`, or `0` if none exist |
| `current_background_path(base_dir, uid)` | `{uid}_background.png` (single cumulative canvas) |

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
