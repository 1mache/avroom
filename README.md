<div align="center">

<img src="react-front/public/avroom.png" alt="AVRoom" width="120">

# AVRoom

**Upload a room photo. Click a chair. It's gone — and now you can move it.**

![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/backend-FastAPI-009688)
![React](https://img.shields.io/badge/frontend-React%2019-61dafb)

</div>

AVRoom is an AI-driven interior design workspace. Point at furniture in a photo, and it's
segmented out and the background is inpainted as if it was never there. The removed object
survives as a draggable cutout you can reposition, rotate, and copy — all in the browser.

## Demo

<!-- docs/media/drag-drop.gif -->
<img src="docs/media/drag-drop.gif" alt="Dragging a cutout around the room" width="800">

<!-- docs/media/rotation.gif -->
<img src="docs/media/rotation.gif" alt="Rotating a cutout via generated 3D model" width="800">

<!-- docs/media/smart-paste.gif -->
<img src="docs/media/smart-paste.gif" alt="Depth-aware smart paste rescaling an object" width="800">

## What it does

- **Object removal** — click an object, pick from candidate masks (or let it guess and pick the best one), and the object is
  cut out while the background is inpainted around the hole.
- **Drag & drop** — reposition any cutout on the canvas.
- **Smart paste** — drop an object anywhere and it rescales to the local depth, optionally
  matching the room's perspective as it moves.
- **2D rotation via novel-view synthesis** — a 3D model is generated from the cutout;
  rotate it and commit an angle to get a freshly rendered 2D view in place.
- **Copy / delete** objects, each tracked independently per room.
- **Projects → Rooms** — rooms are grouped under projects, each with its own preview thumbnail.
- **Export / import** — a project or a single room packs down to a self-contained zip and
  restores on any instance under the caller's account.

## How it works

```mermaid
flowchart LR
    A[Origin Photo] --> B[Depth\nnear/far blend]
    B --> C[Adapt\ndepth → RGB for SAM]
    C --> D[Route\nboundary-variance probe]
    D --> E[Segment\nSAM on depth map]
    E --> F[Refine\nsanitize + dilate]
    F --> G[Inpaint\nLaMa + Stable Diffusion]
    G --> H[Compose\nRGBA cutout]
    H --> I[Background + Cutout]
```

Two rules the pipeline never breaks:

- **SAM sees the depth map, not the RGB photo.** RGB over-segments on fabric creases and shadows.
- **Stable Diffusion refines a native-resolution crop, never the full image** — avoids
  the hallucinations and reimagining of the full room Stable diffusion would otherwise perform.

## Architecture

```mermaid
graph TB
    subgraph Frontend["react-front — React 19 + Vite SPA"]
        FE[Workspace / Dashboard / Projects UI]
    end
    subgraph Backend["fastApi-app — FastAPI (IPE)"]
        API[REST API]
        JQ[(Job dispatcher\nqueued segment/inpaint/3D)]
        PG[(Postgres\nsessions, objects, jobs)]
        Blobs[(Local disk\ncutouts, GLBs, caches)]
    end
    subgraph Pipeline["TestModules — avroom_object_removal"]
        AI[ObjectRemover\ndepth · SAM · inpaint · 3D]
    end

    FE -- fetch --> API
    API --> JQ --> AI
    API --> PG
    API --> Blobs
```

The AI pipeline is imported in-process (`pip install -e ./TestModules`), not a separate service.
Metadata (sessions, objects, jobs) lives in Postgres; blob artifacts (cutout PNGs, GLBs, novel-view
caches) stay on local disk.

## Quick start

```bash
# 1. Start Postgres + Mailpit
docker compose up -d --wait db mailpit

# 2. Python deps (repo root)
python -m venv .venv && .venv\Scripts\activate   # or source .venv/bin/activate
pip install -r requirements.txt

# 3. Apply DB schema
cd fastApi-app
alembic upgrade head

# 4. Run backend + frontend
uvicorn main:app --reload                 # http://127.0.0.1:8000
cd ../react-front && npm install && npm run dev   # http://localhost:5173
```

Windows: `run.bat` does all of the above in one shot (Postgres/Mailpit → migrations → both dev
servers, each in its own terminal).

| Service | Port |
|---|---|
| FastAPI | 8000 |
| Vite dev server | 5173 |
| Mailpit (email preview) | 8025 |
| Postgres | 5433 (not 5432 — see `fastApi-app/.env.example`) |

## Configuration

Copy `fastApi-app/.env.example` to `fastApi-app/.env`. Everything has a sane local default; the
knobs that matter most:

| Var | Purpose |
|---|---|
| `HF_TOKEN` | Hugging Face token — required for 3D reconstruction (Hunyuan3D-2.1 Space) |
| `INFERENCE_WORKERS` | `0` = inline with a process GPU lock, `N` = N parallel inference workers |
| `VALIDATE` | Gate upload validation (technical + content checks); `false` to skip |
| `AUTH_MODE` | `single_user` (default, no login) or `jwt` (real accounts) |
| `DATABASE_URL` | Defaults to the docker-compose Postgres on `localhost:5433` |

## Repo layout

```
avroom/
├── TestModules/    # AI pipeline (avroom_object_removal): depth, segmentation, inpainting, 3D
├── fastApi-app/    # FastAPI backend — API routes, job dispatcher, Postgres models
└── react-front/    # React + TypeScript frontend
```


## Team

[@1mache](https://github.com/1mache) · [@EitanVeryKatz](https://github.com/EitanVeryKatz)
