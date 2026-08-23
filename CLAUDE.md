# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AVRoom (Adaptive Virtual Room)** — AI-driven interior design workspace. Users upload a room photo, click furniture objects, and the system segments them out and inpaints the background. The end vision (per spec) includes drag-and-drop repositioning, NLP-driven edits, and real-time collaboration. **Currently object removal and 2D object rotation (novel-view synthesis) are implemented.**

The spec document (`SpecDocument1.1.pdf` in parent dir) describes the full planned product. Do not implement unplanned features speculatively.

## Repository Structure

```
avroom/
├── TestModules/          # The real AI pipeline (Python package: avroom_object_removal)
│   ├── src/              # Package source (maps to avroom_object_removal namespace)
│   │   ├── core/         # ObjectRemover, interfaces
│   │   ├── ai_engines/   # depth/, segmentation/, inpainting/
│   │   ├── routing/      # Routing strategies for SAM input selection
│   │   └── utils/        # MaskRefiner, DebugImageSaver, MaskOverlapRGBAComposer
│   └── tests/            # Standalone test scripts
├── fastApi-app/          # FastAPI microservice (the IPE - Image Processing Engine)
│   ├── api/routes.py     # upload, segment/inpaint job submission, legacy click endpoints
│   ├── api/jobs.py       # GET /jobs/active, GET/DELETE /jobs/{job_id}
│   ├── core/             # image_processing.py - bridges API to ObjectRemover
│   │   ├── jobs/         # handlers.py (per-kind job bodies) + dispatcher.py (claim loop)
│   │   ├── repositories/ # session_repo.py, job_repo.py - Postgres-backed session/job registries
│   │   ├── auth/         # single_user.py (local dev user) + identity.py (current_user_id() seam)
│   │   └── notifications/ # notify_pipeline_event() - email on inpaint/3D-gen completion
│   ├── db/                # SQLAlchemy models (users/sessions/objects/jobs) + engine/session
│   ├── alembic/           # Postgres schema migrations (`alembic upgrade head`)
│   ├── schemas/          # Pydantic request/response models
│   ├── settings.py       # Storage dirs, DATABASE_URL, auth mode, CORS, etc.
│   └── tmp               # Runtime blob storage — cutouts/GLBs/caches (gitignored; metadata is in Postgres, not here)
└── react-front/          # React/TypeScript frontend (MVP state)
    └── src/
        ├── api/images.ts  # uploadImage(), segmentImage(), inpaintMask() fetch calls
        ├── components/layout/MainPage.tsx  # All UI state lives here
        └── types/         # Shared TypeScript types
```

## Commands

### Backend (FastAPI / IPE)

```bash
# Install all Python deps (includes editable TestModules install)
pip install -r requirements.txt

# Start local Postgres (session/object metadata) — required before the app or its tests will run
docker compose up -d db          # from repo root; host port 5433, not 5432 (see Session & Object Metadata below)
cd fastApi-app
alembic upgrade head             # create/update schema

# Run FastAPI server (from fastApi-app/)
uvicorn main:app --reload
# Runs on http://127.0.0.1:8000

# Type-check (from fastApi-app/)
mypy .
```

### Frontend (React)

```bash
cd react-front
npm install
npm run dev      # Dev server at http://localhost:5173
npm run build    # Production build (tsc + vite)
```

### Tests (TestModules)

```bash
# Run individual pipeline tests from repo root
python TestModules/tests/test_pipeline_runner.py
python TestModules/tests/samMasksTest.py
python TestModules/tests/depthModelTest.py

# Download model weights if missing
python TestModules/tests/downloadTestModelWeights.py
```

## FastAPI Logging

Central config lives in `fastApi-app/logging_config.py`. Call `setup_logging()` once in `main.py` — do not configure logging elsewhere.

**Every new endpoint and processing function must include log calls:**

| Point | Level |
|-------|-------|
| Endpoint entry (key request params) | `INFO` |
| Endpoint success (key response metrics) | `INFO` |
| Pipeline stage start/finish | `INFO` |
| Per-step checkpoints (sizes, shapes, paths) | `DEBUG` |
| Recoverable oddities (empty input, fallback taken) | `WARNING` |
| Failure points immediately before `raise` | `ERROR` |
| Exception handlers (`logger.exception(...)`) | automatic |

Use `logger = logging.getLogger(__name__)` at module level. No `print()`. Level controlled via `LOG_LEVEL` env var (default `INFO`). Output goes to stdout and `fastApi-app/logs/app.log` (gitignored, rotates at 5 MB).

## Shared FastAPI Helpers

Reuse these instead of re-implementing them per module:

- `core/image_codec.py` — `encode_png(array, label)` and `to_base64_ascii(bytes)`. Never hand-roll `cv2.imencode` / `base64.b64encode(...).decode("ascii")` in a route or pipeline function.
- `core/avroom_package.py` — `load_avroom_attr(attr, module=...)` for every deferred `avroom_object_removal` import; it converts a missing install into one `RuntimeError` with the `pip install -e ./TestModules` hint.
- `core/object_storage.py` — all `{uid}_{object_id}_…` path construction, plus `legacy_object_cutout_path` / `legacy_object_glb_path` for pre-numbering names and `remove_file(path) -> int` for "delete if present, count it" loops.
- `core/depth_cache.py` — `memory_image_key(bytes)` builds the `memory://<sha256>` key the AI pipeline caches model state under.
- `settings.py` — `_read_json` / `_write_json` / `load_session_uids` back every JSON sidecar (sessions, names, timestamps); `_env_int` / `_env_float` / `_env_bool` back every env-var getter.

## Session & Object Metadata (Postgres)

Session and object metadata (previously four JSON sidecars — `sessions.json`, `names.json`, `session_timestamps.json`, `object_index.json` — plus one `{uid}_{id}_meta.json` per object) now lives in Postgres. Blob artifacts (cutout PNGs, GLBs, novel-view caches) are unaffected and still live on local disk under `core/object_storage.py`'s path helpers — only *metadata* moved.

- **`db/models.py`** — `User`, `SessionRow` (table `sessions`, the `uid` used everywhere else), `ObjectRow` (table `objects`). `db/session.py` exposes `get_engine()` (per-process lazy singleton) and `session_scope()`.
- **`core/repositories/session_repo.py`** — replaces the old sidecar functions 1:1 by name (`register_uid`, `touch_session`, `set_session_name`, `evaluate_session_sync`, `SessionNotFoundError`, `delete_session`, …), now DB-backed.
- **`core/object_metadata.py`** — same public functions as before (`save_object_metadata`, `get_object_by_uuid`, `list_object_ids`, `build_clone_metadata`, …) but each opens its own short DB session instead of reading/writing a JSON file; `base_dir`/`storage_dir` parameters were dropped since metadata no longer lives under the image storage dir. `list_object_ids` / `next_object_id` moved here from `core/object_storage.py` (they used to scan the filesystem; now they query the `objects` table — the real fix for a `next_object_id` dir-scan race described below).
- **Local dev user**: `AUTH_MODE=single_user` (the default — see `settings.get_auth_mode()`) auto-provisions one fixed user (`local@avroom.dev`, `core/auth/single_user.py::LOCAL_USER_ID`) that every session is attached to. No login, no token, identical UX to before. `AUTH_MODE=jwt` (real per-user auth, ownership checks on every route) is not implemented yet — the schema already supports it (`sessions.user_id` FK), only route-level "who is asking" resolution is still hardcoded to the local user.
- **Local Postgres runs via `docker-compose.yml`** (repo root): `docker compose up -d db`. Host port is **5433**, not 5432 — a native Postgres install may already own 5432 on the host (this bit us during development on Windows). `DATABASE_URL` defaults to `postgresql+psycopg://avroom:avroom@localhost:5433/avroom` accordingly (`settings.get_database_url()`).
- **Schema is managed by Alembic**, not `Base.metadata.create_all()` in application code — run `alembic upgrade head` from `fastApi-app/` after `docker compose up -d db` (both locally and once hosted against RDS) before starting the app. `alembic/env.py` resolves its target DB from `settings.get_database_url()`, the same URL the app itself uses, so there is exactly one place that decides which database this points at. `fastApi-app/tests/conftest.py`'s `_clean_database` fixture is the one exception: it calls `Base.metadata.create_all()` directly and truncates every table before each test, since tests want a schema-matches-models guarantee and per-test isolation, not migration history.
- **Tests never run against the dev database.** `conftest.py`'s `_use_test_database()` runs at import time (before any test module or `db.session.get_engine()` can execute) and repoints `DATABASE_URL` at `<dbname>_test` (e.g. `avroom_test`), creating that database via a maintenance connection if it doesn't exist yet. This exists because `_clean_database` truncates `objects`/`sessions`/`users` before every test, and `settings.get_database_url()`'s default is otherwise identical between app and test process — without the swap, running `pytest` against a normal local setup wipes live session data. Gotcha if touching this: `str(sqlalchemy.engine.URL)` masks the password as `***`; building the env var string requires `url.render_as_string(hide_password=False)`.
- `save_object_metadata` auto-provisions its session row (owned by the local user) if the session hasn't been registered yet, matching the old sidecars' decoupled behavior where object metadata and session registration were independent files.

Three races the old filesystem/JSON approach had are now closed: `next_object_id` (used to be a dir-scan max, now a DB query — still relies on the existing canvas-writer lock to serialize concurrent inpaint/duplicate per session on a single instance, see `docs/backend/concurrency.md`, rather than a row lock); `count_clones_of_root` (used to be an O(n) per-file JSON read, now `COUNT(*)`); `PATCH /images/objects/{uuid}` (still a read-then-write, but against one row under the object's own uuid rather than a shared JSON file).

## Durable Job Queue

Segment, inpaint, and 3D generation are **queued, not blocking**. `POST /images/segment`, `POST /images/inpaint`, and `POST /3d/test-3d` insert a `JobRow` (`db/models.py`, table `jobs`) and return `202 {job_id}` immediately — no route does GPU work on the request thread anymore. Full mechanics, including the two Mermaid sequence diagrams and the region-lease interaction, live in `docs/backend/concurrency.md`; the summary:

- **`core/repositories/job_repo.py`** — `create_job`, `claim_next_job` (`SELECT ... FOR UPDATE SKIP LOCKED ORDER BY created_at`, plain FIFO across every user/session), `finish_job`/`fail_job`/`delete_job`, `list_session_jobs`, `list_active_jobs`, `reserved_mask_ids`, `mark_running_orphans_failed` (the startup sweep — a `running` row with no live process behind it becomes `failed`; `queued` rows need no sweep, a fresh dispatcher just claims them).
- **`core/jobs/handlers.py`** — `run_segment_job` / `run_inpaint_job` / `run_generate_3d_job`: the former route bodies verbatim, including the canvas-writer/region-lease sandwich inpaint always used. A handler raising `SessionConflictError` becomes job status `"conflict"` (what used to be an HTTP 409); anything else becomes `"failed"` with the exception text in `error`.
- **`core/jobs/dispatcher.py`** — `max(1, INFERENCE_WORKERS)` daemon threads polling `claim_next_job()` every 0.5s. Started/stopped in `main.py`'s lifespan, alongside `mark_running_orphans_failed()` on startup.
- **Result shape**: a successful `inpaint`/`generate_3d` job **deletes its own row** — the `ObjectRow` / GLB file already *is* the durable result. A successful `segment` job stays `done` with `result={"mask_ids":[...]}` until consumed (an inpaint submitted with `from_job_id`) or dismissed (`DELETE /jobs/{job_id}`) — **several segment results can be queued at once**, consumed one at a time.
- **Delivery is polling, not push**: `POST /images/{uid}/sync-check` now also returns that session's `jobs` list (unconditionally, not gated on `needs_refresh` — a job's status can change without bumping `last_changed`); `GET /jobs/active` is the same idea across every session for the dashboard's per-card dot; `GET /jobs/{job_id}` inflates a done segment job's `mask_ids` into full candidates on read.
- **Identity seam**: `core/auth/identity.py::current_user_id()` resolves "who is asking" — today it always returns the fixed local user (same as `session_repo._get_or_create_session_row`, which now calls this too instead of `core.auth.single_user` directly), but it is the **one** function a future `AUTH_MODE=jwt` needs to change. Every `/jobs` route and all three submit routes depend on it; job listing/reads filter `WHERE user_id = :caller`, which is the entire result-routing mechanism for multiple users sharing one queue.
- **The pinning fix**: `reserved_mask_ids(session_id)` (in `job_repo.py`) protects mask ids belonging to an unconsumed `done` segment job **and** to any `queued`/`running` inpaint job, unioned with the existing in-memory `pinned_mask_ids` at the segment call site. This exists because queuing widened a real race — a submitted inpaint can now sit `queued` for an arbitrary time before a dispatcher thread actually takes its in-memory lease, so a concurrent segment's candidate wipe needs to know about that not-yet-running inpaint too, not just live leases.
- **Novel-view rotation is deliberately NOT queued** — it stays exactly as it was (a detached blocking request with a local `rotation` marker on the object; see "Rotation flow" below).

## Python Code Style

- **Python 3.11**, type-checked with **mypy**.
- Declare types with annotations on all function signatures and class attributes. Skip only when redundant (e.g., `x = 0` needs no `: int`).
- Document all public functions and classes with docstrings. Explain *what* and *why*, not just *what the name already says*.
- Use `from __future__ import annotations` at the top of every Python file.
- All Pydantic models use `Annotated[Type, Field(...)]` style.

## AI Pipeline Architecture (Critical)

`ObjectRemover` (`TestModules/src/core/objectRemover.py`) orchestrates the legacy full pipeline. Normal UI flow now uses `ObjectSegmentor` first, lets the user choose a mask, then passes selected `refined_mask` to `BackgroundInpainter`.

1. **Depth** — `OptimizedDepthFacade` blends two depth models (Depth-Anything-V2 for near, LiheYoung for far) using V2 depth values as alpha weights. This prevents wall seams.
2. **Adapt** — `SamImageAdapter` converts the grayscale depth map to 3-channel RGB for SAM input. Result is cached per image+point.
3. **Route** — `BoundaryVarianceRoutingStrategy` probes a tight SAM mask, measures depth variance along its boundary ring, and decides expand pixels + whether the object is 3D. Returns a `run_context` dict.
4. **Segment** — `SamFacadeSingleton` (loaded once, Singleton) receives the adapted depth map (NOT the RGB image) and returns a mask.
5. **Refine** — routing `expand_pixels` (sanitize-then-dilate) plus `MaskRefiner.expand_mask_uniform(radius=3)`. Verifier may grow further via `mask_dilate_pixels` on retry.
6. **Inpaint** — `HybridInpainter` (LaMa primary + Stable Diffusion with `sd_strength=0.40`, 42 steps).
7. **Compose** — `MaskOverlapRGBAComposer` extracts the cutout as BGRA with alpha=0 outside the mask.

### Rules Never to Break

- **SAM receives depth map, not RGB.** RGB causes over-segmentation on fabric creases and shadows. The adapter exists for this reason.
- **Near-Far blending is alpha compositing, not averaging.** V2 depth values serve as the alpha weight. Do not simplify to a mean.
- **Sanitize before any dilation.** Dilating a dirty SAM mask bridges detached speckles into floor/chair. Use `sanitize_then_expand` / keep-click-component first; the ~3 px refine is only an edge pad.
- **SD runs on a native-resolution crop, never the squashed full frame.** `StableDiffusionInpaintingStrategy` crops around the mask with `mask_crop_window`, generates at /8-snapped native dims, and pastes only mask pixels back. Squashing a 1600×1200 frame to 512×512 causes a 3× upscale smear and a paste seam that no SD knob can fix. Only mask pixels are written back; surroundings stay byte-identical so Gemini's dual-crop verifier sees an uncorrupted reference.

## FastAPI ↔ TestModules Integration

`fastApi-app/core/image_processing.py` imports `ObjectRemover` from the `avroom_object_removal` package (installed via `pip install -e ./TestModules`). If the package is missing, the server raises `RuntimeError` with an install hint. Image bytes are passed directly to `remover.remove_object(image_path=..., image_bytes=...)` using a `memory://sha256` key so models can cache without disk reads.

Uploaded images are stored in `fastApi-app/tmp/images/{uuid}.ext`. Debug overlays go to `fastApi-app/tmp/images/`.

### Upload validation (two-stage gate)

`POST /images/upload` validates before persisting:

1. **Technical** — `fastApi-app/core/image_validation/` (`ImageValidator`): format/MIME, size, decode, resolution, blur, exposure, alpha emptiness, uniform scene. Env thresholds via `UPLOAD_*` in `settings.py`. Fail → HTTP 422, no disk write.
2. **Content** — `ContentImageValidator` + `ContentValidationFacade` (CLIP zero-shot default) via inference pool job `VALIDATE_CONTENT`. Fail → HTTP 422, no disk write.

Set `VALIDATE=false` before starting the server to skip both stages (default: `VALIDATE=true`).

Not wired into segment/inpaint/removal pipelines.

### Debug vision endpoints

`POST /debug/validate`, `POST /debug/depth-map`, `POST /debug/normal-map`, and `POST /debug/sam-everything` (`fastApi-app/api/debug_vision.py`) are test/inspection tools, not production flow — no session, no disk writes. They accept a multipart `file` upload and are gated by `DEBUG_ENDPOINTS` (`settings.get_debug_endpoints_enabled`, default enabled; `false` → 404). The React frontend has a dedicated screen for these — see `DebugScreen` under Frontend Notes below.

- `/debug/validate` runs the **full** validation scoreboard (`ImageValidator.validate_all` — every technical check plus the CLIP content checks, never stopping at the first failure, unlike `POST /images/upload`'s `validate()`) and always returns 200 JSON (`DebugValidationResponse`) — a failed check is data, not an error.
- `/debug/depth-map?strategy=anything|blended|enhanced_edge&model=...&colormap=none|inferno|magma|turbo|jet` renders one of three depth strategies as a PNG via `avroom_object_removal.utils.colorize_depth`. `strategy=anything` is `DepthAnythingMappingStrategy(model)` (the only one honoring `model`); `blended`/`enhanced_edge` are the actual multi-checkpoint strategies production uses (`NearFarBlendedDepthMappingStrategy` / `EnhancedEdgeDepthMappingStrategy`, production's true default).
- `/debug/normal-map?hub_model=metric3d_vit_small|metric3d_vit_large|metric3d_vit_giant2` runs `Metric3DNormalMappingStrategy` and returns a PNG via `colorize_normals` (`JobKind.DEBUG_NORMAL_MAP`). DebugScreen clicks sample approximate nx/ny/nz from the 8-bit PNG.
- `/debug/sam-everything?source=depth|rgb&depth_strategy=...&points_per_side=16&pred_iou_thresh=0.88&stability_score_thresh=0.95&min_mask_region_area=0&alpha=0.45` runs `SamSegmentationStrategy.predict_everything` (wraps `SamAutomaticMaskGenerator`, reusing the already-loaded `SamPredictor` weights via a second `functools.lru_cache`'d loader, now keyed on all four quality-threshold args too) and renders the masks via `avroom_object_removal.utils.overlay_masks` (deterministic per-mask color, translucent fill + outline) composited onto the original photo. `source=depth` (default) feeds SAM the same `SamImageAdapter`-adapted depth map production uses; `source=rgb` feeds the raw photo instead, to visually demonstrate why the depth-map rule exists (visibly more/noisier masks from fabric creases and shadows).
- All three dispatch through the inference pool (`/debug/validate`'s content stage reuses `JobKind.VALIDATE_CONTENT`; the two PNG endpoints are `JobKind.DEBUG_DEPTH_MAP` / `DEBUG_SAM_EVERYTHING`, in `_FACADE_JOB_KINDS` so inline mode takes the GPU lock) — same concurrency model as every other model call, see `core/inference_pool/`.
- `predict_everything` is on `ImageSegmentationStrategy` as a non-abstract method (default raises `NotImplementedError`) since prompt-free segmentation is SAM-specific, not a general strategy capability. `ImageSegmentationFacade.get_all_masks_for_image` exposes it at the facade level, alongside the existing point-prompted `get_mask_at_point` / `get_all_masks_for_position`.
- `X-Mask-Count`/`X-Elapsed-Ms` response headers require `expose_headers` on the CORS middleware (`main.py`) — `allow_headers` only covers request headers, so without it browser JS reads both as `null`.

## 3D Reconstruction (Hunyuan3D-2.1)

`TestModules/src/ai_engines/reconstruction_3d/` (part of the `avroom_object_removal` package — there is no separate 3D package anymore) owns image-to-GLB generation via `Reconstruction3DFacade`. **Default primary backend is `Hunyuan3D2ReconstructionStrategy`**, which calls Tencent's Hunyuan3D-2.1 model **via a public Hugging Face Space** (`gradio_client`, default space id `es3d-fi/hunyuan3d-2-1`, a mirror of `tencent/Hunyuan3D-2.1`). If the primary call raises, the facade automatically retries once against `TriposrReconstructionStrategy` (local PyTorch, `stabilityai/TripoSR` weights) with identical arguments before giving up. OpenLRM, Trellis (Microsoft's Trellis 2, the previous default before this backend was swapped in), and VFusion3D also exist as strategies but are reachable only by injecting them explicitly into `Reconstruction3DFacade(...)` — the facade never constructs them on its own.

Public API: `Reconstruction3DFacade().generate(image, *, quality=ReconstructionQuality.HIGH, output="bytes")`. Accepts BGRA `np.ndarray` from `ObjectRemover`, PNG `bytes`, `PIL.Image`, or `pathlib.Path`. Returns GLB as `bytes` / `Path` / `BytesIO`.

The Hunyuan3D-2.1 Space is queued; one generation takes tens of seconds of compute plus queue wait. **Wired into FastAPI** via `core/inference_pool` (`JobKind.GENERATE_3D`) from two call sites: `POST /3d/test-3d` (`fastApi-app/api/model_3d.py`, now itself a durable job — see "Durable Job Queue" above — that queues a `generate_3d` `JobRow` and returns `202`) and `POST /images/novel-view` (`fastApi-app/api/novel_view.py`, still a direct blocking call, via the shared `core/object_3d.py::ensure_object_glb` cache-or-generate helper both call sites use). It is not part of the `/images/click`/`/images/inpaint` object-removal path.

See [docs/ai-pipeline/ai-engines/reconstruction-3d/README.md](docs/ai-pipeline/ai-engines/reconstruction-3d/README.md) for the full strategy list, quality-preset mapping, and error types.

## Email Notifications on Pipeline Completion

`core/notifications/notify_pipeline_event(uid, event, *, ok=True, detail=None)` emails a
session's owner when a slow AI operation finishes — currently wired at the two call sites that
warrant it: inpainting (`api/routes.py`, after the object is persisted) and 3D generation
(`api/model_3d.py`, after the GLB is written), both on success and on failure. It is deliberately
**not** a generic hook on every AI call — segment/click/upload are sub-second and the user is
still watching the response.

The function takes no dependency on `core.inference_pool` (a free-form `event` string, not a
`JobKind`) so it can be called from anywhere, including the AI pipeline rewrite happening in
parallel on another branch. It never raises and never blocks the request: the send happens on a
daemon thread, and any failure (missing recipient, dead mail server) is logged at `WARNING` and
swallowed — a notification failing must never turn an already-successful AI request into a 500.

The email body/subject always name the session — its display name, falling back to the uid when
unnamed (`core/repositories/session_repo.py::get_session_notify_target`) — so the recipient can
tell which room finished.

**Transport is zero-config in both environments**, chosen by `settings.get_notify_backend()`:
```
NOTIFY_BACKEND unset  →  "ses" if STORAGE_BACKEND == "s3" else "smtp"
```
No dedicated env var needs setting — it rides the same switch a cloud deploy already flips.
Local (`smtp`) talks to a **Mailpit** container (`docker-compose.yml`'s `mailpit` service, started
by `run.bat` alongside Postgres) — no auth, no TLS, no credentials; every notification is viewable
at `http://localhost:8025`, nothing reaches a real inbox. Cloud (`ses`) uses **boto3 SES**
(`core/notifications/ses_backend.py`; boto3 is already a dependency for the `STORAGE_BACKEND=s3`
path) — credentials resolve from the deployed instance's IAM role, nothing in env either. All
seven `NOTIFY_*`/`SMTP_*` vars in `.env.example` are optional overrides, not required config.

The local dev user's email (`core/auth/single_user.py::LOCAL_USER_EMAIL`) is
`avroom-team@proton.me` — the team inbox — not a personal address; local notifications land in
Mailpit regardless, so this only matters if `NOTIFY_ENABLED=false`/Mailpit is bypassed. Alembic
migration `0002_local_user_email` updates the row on machines that provisioned the local user
before this change.

## Frontend Notes

The product has **two screens plus an upload step, plus a separate debug screen**: `DashboardScreen` (session list, new-session entry, session delete), `UploadScreen` (file intake between dashboard and workspace), `WorkspaceScreen` (the editor), and `DebugScreen` (upload a photo, see the full validation report plus rendered depth-map/SAM output — no session created; see "Debug vision endpoints" above). `App.tsx` switches between them with a local discriminated-union `Route` state (`{screen:"dashboard"} | {screen:"upload"} | {screen:"workspace", uid} | {screen:"debug"}`) — no router library, no auth. The dashboard is home (`App` boots into it); `WorkspaceScreen` is mounted `key={uid}` so switching sessions remounts it cleanly rather than reusing state. The Toolbar's back arrow calls `onExit`, which routes back to the dashboard — it is enabled, not disabled. `DashboardScreen`'s header carries a right-aligned flask-icon button (`onOpenDebug`) that routes to `DebugScreen`, always visible regardless of whether the backend's `DEBUG_ENDPOINTS` is on (a disabled backend surfaces as a 404 inside each panel, not a hidden button).

- API base URL defaults to `http://127.0.0.1:8000`; override with `VITE_API_BASE_URL` env var. `DashboardScreen`'s session-list fetch shows an offline state with a retry action on failure; `WorkspaceScreen`'s own session boot shows a plain "Opening the session" placeholder on the stage while loading and falls back to `sessionName = uid` if the cache-status fetch fails (no dedicated offline UI there).
- Click coordinates are translated from display-space to natural image-space before sending to the API. All the contain-fit ↔ natural-pixel conversions live in `src/utils/stageGeometry.ts` (`getContainedImageRect`, `toNaturalPoint`, `clampCutoutOffset`, `getBoundsStageRect`, `buildHitTestOrder`, `compositePreviewOntoCanvas`) — reuse them rather than re-deriving the math.

### Workspace layout (Photoshop-inspired)

- **The photo is the screen.** `.stage` fills everything under the toolbar and the image is `object-fit: contain`, so it renders at max size without distortion and letterboxes when the aspect ratio demands it. `.stage-canvas-edge` traces the rendered image rect with a hairline + cast shadow so the photo reads as a sheet on the graphite surround.
- **`Toolbar`** (`components/workspace/Toolbar.tsx`) is the only permanent chrome, always visible: back arrow (returns to the dashboard), editable session name (Enter saves), then icon-only tools — cutout (scissors), rotate, copy, smart-paste toggle — and a red trash at the far right. Icons carry no text; they name themselves on hover through the shared `[data-tip]` CSS tooltip. Everything object-scoped (rotate, copy, smart paste, delete) greys out instead of disappearing when nothing is selected, so the row never reflows.
- **Cutout is armed, not confirmed.** Pressing scissors sets `cutMode`; the next click on the photo becomes the segmentation seed and fires `runSegment` immediately, disarming the tool. Escape cancels. There is no separate "Cut Out" button any more.
- **Smart paste is a stub** — a local boolean with no behavior behind it; drag-and-drop is still plain dragging.
- **Trash arms a confirm dialog, then permanently deletes.** Clicking it opens a `ConfirmDialog` in `WorkspaceScreen`, not an immediate delete — deletion calls `DELETE /images/objects/{uuid}` and can't be undone. On confirm, `useSessionJobs.deleteObject` awaits the request (uuid-keyed, same precondition as duplicate — pre-UUID objects can't be deleted), then removes the object locally on success; failure surfaces through the generic error modal. The backend removes the cutout, GLB, novel-view caches, and metadata, but **never repaints the background** — the inpainted hole stays. Object ids can be reused after deletion (`next_object_id` is `max(existing)+1`).
- **`ObjectRail`** (`components/workspace/ObjectRail.tsx`) replaces the old `ObjectPanel`. It hides in the right screen edge and slides out on hover of that edge, retracting after a ~220 ms grace once the pointer leaves (suppressed while a rename input is focused). Retracted, its spine still shows one notch per object — bright for the selected one, grey for hidden, pulsing while work is in flight, red for a failed job. Each row carries an eye toggle, and a revert toggle when that object has a rotation result. It also takes the session's `jobs` list directly (not a `pending: PendingEntry[]` prop anymore — see "Concurrent job state" below): queued/running jobs render as spinner rows labeled by kind (`Segmenting`/`Removing`/`Building 3D`), failed jobs render as dismissible red rows (`onDismissJob`, `DELETE /jobs/{job_id}`).
- **Design tokens** live at the top of `src/style.css`: graphite chrome (`--chrome-*`), cyan accent (`--cyan`, `--cyan-bright`), IBM Plex Sans for UI and IBM Plex Mono for counters/status readouts (loaded in `index.html`). Radii stay at 2–3 px throughout.

### Multi-object preview & selection model

All segmented objects for a session stay composited on the inpainted background simultaneously (each `CutoutObject` has its own `hidden` flag and drag `offset`; visibility stays local-only, but `offset` is now persisted — see below — the cumulative canvas returned by `/images/inpaint` already has every object removed, so the frontend just layers cutout PNGs back on top of it). Key points if touching this area:

- **Selection** (`selectedObjectId`) is independent of visibility. It starts `null` (no selection) on fresh upload *and* on session restore. Set by clicking an object's thumbnail in `ObjectRail`, or by clicking/dragging it directly in the preview stage. Hiding the selected object clears selection. A newly created object auto-selects.
- **Hit-testing is alpha-precise, not DOM stacking.** Cutout PNGs are full-image-sized with transparency outside the object, so a topmost DOM overlay would swallow every click. `WorkspaceScreen.tsx` builds an offscreen `<canvas>` per object (`hitCanvasesRef`) and samples pixel alpha on pointer-down to find which object (if any) was clicked, testing the selected object first, then remaining visible objects topmost-first. The cutout `<img>` elements themselves are `pointer-events: none`; a single transparent `.stage-input` div owns pointer-down handling.
- **The 3D viewer (`Model3DFrame`) is an angle picker for rotation, not a standalone preview.** Pressing the toolbar's **Rotate** button is scoped to the selected object only; changing selection always forces `rotateMode` back to `false`. The GLB itself is still generated/cached exactly as before (`glbData` per object, via `POST /3d/test-3d` / `GET /3d/{uid}/{objectId}`) — only its purpose changed.
- Eye-toggle button lives in `ObjectRail` per row (`onToggleHidden`); hidden objects are excluded from render, hit-testing, and selection.
- **While `rotateMode` is on, the 3D model replaces the selected object's 2D cutout in place**, not a full-stage overlay — same z-index/rect trick as before (`model3DFrameStyle` from `cutoutAlphaBounds` + `offset`, `Model3DFrame` above `.stage-input` so `OrbitControls` receive pointer events). The selected object's 2D `<img>` is skipped from render (`stageObjects`) and hit-testing while `rotateMode` is true.
- **Rotation flow:** orbiting measures azimuth/elevation deltas from the viewer's starting pose, around the object center (`OrbitControls.target` pinned to `(0,0,0)`, panning disabled). Pressing **Rotate** again (or Enter) calls `Model3DFrame`'s `capture()` for the angle delta + a canvas snapshot, closes the picker, and fires `useSessionJobs.commitRotation` **detached** against `POST /images/novel-view` — the object's `rotation` field (`{ pose, previewSrc, src, bounds, status }`) is the pending marker; the snapshot shows immediately and is swapped for the real synthesized PNG when the response lands. Escape cancels with no request. A per-object **Show original** checkbox toggles the selected object's rotated result back to its pristine cutout. Rotating again always starts over from the pristine cutout — the backend never overwrites `{uid}_{object_id}_cutout.png` in the rotate path, only caches separate `..._novel_az{az}_el{el}.png` files.
- **`rotation` is local-only state, like `glbData`** — it must never be written into `cutoutSrc`/`cutoutAlphaBounds` directly, since `useSessionSync`'s reconcile unconditionally overwrites those two fields from server truth on every sync tick. `types/session.ts`'s `effectiveCutoutSrc`/`effectiveCutoutBounds` are the single place that decide, per object, whether to show the original cutout or the rotated result — used consistently by the stage render, hit-testing, drag-clamp bounds, and `ObjectPanel` thumbnails. `hitCanvasesRef` invalidates its cached alpha canvas when an object's effective src changes (not just when its id first appears), since rotation changes the silhouette in place.
- **`offset` is persisted, unlike the other local-only fields above.** `WorkspaceScreen.tsx`'s `finishDrag` fires `setObjectOffset(uuid, x, y)` once per drag (not per pointermove) against `PATCH /images/objects/{uuid}`, and `useSessionJobs.loadRestoredObjects` reads it back from `ObjectInfo.offset_x`/`offset_y` on session restore instead of resetting to `(0, 0)`. The backend endpoint (`update_object` in `api/routes.py`) is a general partial-update PATCH shared with rename — it uses `request.model_fields_set` to tell "field omitted" from "field explicitly `null`" (`name: null` clears the name; an omitted `offset_x`/`offset_y` leaves it alone), so a drag-persist call and a rename call can never clobber each other's field. Duplicating an object computes a nudged `offset_x` server-side, atomically with clone creation (`core/object_metadata.py::_nudge_clone_offset`) — the clone lands ~15% of its own width to the left of its source (or right, if there's no room left), not exactly on top of it.

### Concurrent job state (`src/hooks/`)

Segment and inpaint are queued server-side now (see "Durable Job Queue" above): `segmentImage`/`inpaintMask` return `{job_id}` immediately, and the *result* — mask candidates, or the finished object — shows up later via polling. This is what makes work submitted right before navigating away from a session survive: it's a durable Postgres row, not React state, so re-entering the session (or the next sync tick, if you're still there) picks it back up instead of the result being silently dropped on an unmounted component. Three hooks split the concern:

- **`useSessionJobs`** owns `objects`, `selectedObjectId`, and `jobs: JobInfo[]` (fed from `useSessionSync`, replaced wholesale each poll — `JobInfo` carries no local-only fields to preserve, unlike `objects`). `runSegment`/`selectMask` just submit and return — no local loading state, no single-flight restriction; several segment clicks in a row all queue. A **picker-chain effect** watches `jobs` for the oldest not-yet-dismissed `done` segment job and opens `MaskPickerModal` on it; `dismissedSegmentJobIdsRef` (reset on remount) tracks pickers closed without choosing, so re-entering a session replays the same chain. `selectMask(jobId, maskId)` submits inpaint with `from_job_id: jobId` so the source segment row is consumed atomically. `hasPendingWork` is `jobs.some(status is queued/running) || isDuplicating || isDeleting || any rotation pending`. A **conflict effect** watches `jobs` for a job that resolved to status `"conflict"` and fires `onConflict` once per job (routed to `useConflictNotices`, the same inline notice a synchronous 409 used to produce) then auto-dismisses that row. The out-of-order-response guard `highestCommittedObjectIdRef` used to protect (`selectMask`'s own response applying an older `background_b64` over a newer one) is now moot: `backgroundSrc` no longer comes from a specific job's response at all, only from `useSessionSync`'s reconcile re-fetching current cache status — there is nothing left to arrive out of order. The ref still exists, tracking the high-water object id for `duplicateObject`/`loadRestoredObjects`. An `imageIdRef` check in every callback drops stale results if the user switched sessions mid-flight.
- **`useSessionSync`** polls `POST /images/{uid}/sync-check` every ~2s while `hasPendingWork` is true, plus once on window focus/visibilitychange — idle sessions never poll. Every response's `jobs` field is applied to `useSessionJobs`'s `jobs` state **unconditionally**, not gated on `needs_refresh` — a job moving `queued → running → done` doesn't bump the session's `last_changed` (only object/session mutations do), so `needs_refresh` can stay `false` across an entire job's lifecycle. On `needs_refresh` specifically, it also re-fetches `/objects` + `/cache` and **merges** into local object state rather than replacing it: existing objects keep their local `offset`/`hidden`/`glbData`, new ones are appended, vanished ones are dropped (clearing selection if selected). The background URL gets a `?t=<lastChanged>` cache-bust query param on reconcile. `recordLocalMutation` (an alias for the same check) is also called after every local mutation (upload, job submit, rename, session rename) to seed `lastChanged` early.
- **`useConflictNotices`** turns a job's `"conflict"` status (mask overlaps an in-flight removal, segment click inside a lease, canvas-writer timeout — same causes as the old synchronous 409, just detected later, at execution instead of submit) into a dismissible, auto-expiring inline notice instead of the modal error dialog. Any error that isn't an `ApiError` with `status === 409` is rethrown, landing back in the caller's `try/catch` and the normal error modal — `WorkspaceScreen`'s `handleJobConflict` manufactures that `ApiError(409, ...)` shape from the job's `error` text so this hook doesn't need to know jobs exist. `setSessionName`'s 409 (duplicate name) is a different, real conflict and is never routed through this hook.

3D generation (`POST /3d/test-3d`) is also queued now but is **not** watched through `useSessionJobs`/`jobs` — `WorkspaceScreen.handleRotate` submits it directly (`submitGenerate3D`) and awaits `waitForJobDone` (a small poll loop in `api/images.ts`, 800ms interval) before reading the GLB back via `fetchCached3DModel`, preserving the existing awaited-under-a-spinner UX (`isPreparing3D`). `waitForJobDone` treats a 404 as success, not failure: a successful `generate_3d` job's row is deleted by the dispatcher (same as inpaint — its real result is the GLB file, already on disk by the time the row disappears), and this is only safe because the caller polls a job id it just submitted itself.

`api/images.ts`'s `handleJsonResponse` throws a typed `ApiError` (with `.status` and `.detail` parsed from FastAPI's `{"detail": ...}` envelope) instead of a plain `Error`, so callers can distinguish 409 from a real failure by status code rather than string-matching the message.

### Dashboard preview thumbnails

`GET`/`POST /images/{uid}/preview` (`fastApi-app/api/routes.py`) back the session card thumbnail — a JPEG of the room roughly as the user left it. `POST /images/upload` writes an initial one (downscaled original) via `core/session_preview.py::write_upload_preview` so a card is never empty. `WorkspaceScreen.tsx`'s `capturePreviewRef` composites background + every visible cutout at its current offset (`utils/preview.ts::composeSessionPreview`, canvas-based, 640px long edge, JPEG q0.82) and calls `saveSessionPreview` debounced 500ms (`PREVIEW_DEBOUNCE_MS`) after any mutation settles — wired through `onMutated` for inpaint/rotation/rename/duplicate/delete/hide, and directly from `finishDrag` for drag-end (drags never go through `useSessionJobs`, so `onMutated` alone doesn't cover them). The POST never calls `touch_session` — it fires well after the mutation that already bumped `last_changed`, so the dashboard's `?t=` cache-buster is already correct.

## Planned but Not Yet Implemented

Per the spec, the following are planned but absent from the codebase:
- Java SpringBoot core server (auth, project management, DB)
- S3 blob storage (Postgres metadata is implemented — see "Session & Object Metadata (Postgres)" above; blobs are still local disk only)
- Collaboration (Spectator/Partner/CoAdmin roles, Operational Transformation)
- Drag-and-drop / Smart Paste
- Depth adjustment
- NLP/prompt-based generative editing
- Obstruction detection
