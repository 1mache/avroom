# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AVRoom (Adaptive Virtual Room)** — AI-driven interior design workspace. Users upload a room photo, click furniture objects, and the system segments them out and inpaints the background. The end vision (per spec) includes drag-and-drop repositioning, NLP-driven edits, and real-time collaboration. **Currently only object removal is implemented.**

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
│   ├── api/routes.py     # upload, segment, inpaint, legacy click endpoints
│   ├── core/             # image_processing.py - bridges API to ObjectRemover
│   ├── schemas/          # Pydantic request/response models
│   ├── settings.py       # Image storage dir config
│   └── tmp               # Runtime temp object storage (gitignored)
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

# Run FastAPI server (from fastApi-app/)
cd fastApi-app
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
5. **Refine** — `MaskRefiner.expand_mask_uniform(radius=3)` applies uniform dilation to cover missed edge pixels.
6. **Inpaint** — `HybridInpainter` (LaMa primary + Stable Diffusion with `sd_strength=0.35`).
7. **Compose** — `MaskOverlapRGBAComposer` extracts the cutout as BGRA with alpha=0 outside the mask.

### Rules Never to Break

- **SAM receives depth map, not RGB.** RGB causes over-segmentation on fabric creases and shadows. The adapter exists for this reason.
- **Near-Far blending is alpha compositing, not averaging.** V2 depth values serve as the alpha weight. Do not simplify to a mean.
- **Mask dilation prevents LaMa halo.** LaMa bleeds object pixels into background with tight masks. Always dilate before inpainting.

## FastAPI ↔ TestModules Integration

`fastApi-app/core/image_processing.py` imports `ObjectRemover` from the `avroom_object_removal` package (installed via `pip install -e ./TestModules`). If the package is missing, the server raises `RuntimeError` with an install hint. Image bytes are passed directly to `remover.remove_object(image_path=..., image_bytes=...)` using a `memory://sha256` key so models can cache without disk reads.

Uploaded images are stored in `fastApi-app/tmp/images/{uuid}.ext`. Debug overlays go to `fastApi-app/tmp/images/`.

## Trellis 2 3D Generation

`TrellisModule/` (package `avroom_trellis`) wraps Microsoft's Trellis 2 image-to-3D model **via the public Hugging Face Space** (`microsoft/TRELLIS.2`) using `gradio_client`. Local install is not supported on this machine (Linux + 24 GB VRAM only).

Public API: `Trellis3DGenerator().generate(image, *, quality=Quality.FAST, output="bytes")`. Accepts BGRA `np.ndarray` from `ObjectRemover`, PNG `bytes`, `PIL.Image`, or `pathlib.Path`. Returns GLB as `bytes` / `Path` / `BytesIO`.

The Space is queued (Zero GPU). One generation takes seconds of compute plus queue wait. Module is **not** wired into FastAPI yet.

Install: `pip install -e ./TrellisModule` (or `pip install -r requirements.txt` which includes it).

## Frontend Notes

- Frontend is **MVP**: single page (`MainPage.tsx`), no routing, no auth.
- All state managed with `useState` in `MainPage.tsx`. `UploadFrame` and `ResultFrame` are pure display components.
- API base URL defaults to `http://127.0.0.1:8000`; override with `VITE_API_BASE_URL` env var.
- Click coordinates are translated from display-space to natural image-space before sending to the API.

## Planned but Not Yet Implemented

Per the spec, the following are planned but absent from the codebase:
- Java SpringBoot core server (auth, project management, DB)
- PostgreSQL + S3 storage
- Collaboration (Spectator/Partner/CoAdmin roles, Operational Transformation)
- Drag-and-drop / Smart Paste
- Object rotation, depth adjustment
- NLP/prompt-based generative editing
- Image validation (blurriness, room detection)
- Obstruction detection
