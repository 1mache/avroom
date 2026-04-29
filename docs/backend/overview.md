# Backend Overview

The backend is a small FastAPI service whose only job is to expose the AI pipeline over HTTP and manage uploaded images on disk.

## App entry — [`fastApi-app/main.py`](../../fastApi-app/main.py)

```1:32:fastApi-app/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as images_router

app = FastAPI(
    title="Image Processing Service",
    version="0.1.0",
    description=(
        "MVP FastAPI microservice for image upload and click-based operations. "
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def read_root() -> dict[str, str]:
    """Health/info endpoint for the image processing service."""

    return {"status": "ok", "service": "image-processing"}


app.include_router(images_router)
```

Things to notice:

- The CORS list is hardcoded to the Vite dev server (`localhost:5173` / `127.0.0.1:5173`). If the frontend ever moves origins, this needs updating.
- There is exactly one router (`/images`) — see [api-endpoints.md](api-endpoints.md).
- `GET /` is a health endpoint that returns `{"status": "ok", "service": "image-processing"}`.

## Module map

| Module | File | Purpose |
|---|---|---|
| Entry / app factory | [`fastApi-app/main.py`](../../fastApi-app/main.py) | `FastAPI()` instance, CORS, mount router. |
| Settings | [`fastApi-app/settings.py`](../../fastApi-app/settings.py) | `get_image_storage_dir()` — see [settings-and-storage.md](settings-and-storage.md). |
| Routes | [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) | `/images/upload` and `/images/click`. |
| Core | [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) | Bridges HTTP requests to `ObjectRemover.remove_object`. |
| Schemas | [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py) | Pydantic models. |

## Project metadata — [`fastApi-app/pyproject.toml`](../../fastApi-app/pyproject.toml)

```1:2:fastApi-app/pyproject.toml
[tool.fastapi]
entrypoint = "main:app"
```

That is the entire file. There is **no** `[project]` block here — runtime dependencies are pinned in the root [`requirements.txt`](../../requirements.txt). The `main:app` hint is what `fastapi-cli` uses for `fastapi run`.

## How to run it

From `fastApi-app/`:

```bash
uvicorn main:app --reload --port 8000
```

For the pipeline call to actually succeed you also need the AI pipeline installed:

```bash
pip install -e ./TestModules
```

(Already declared on line 1 of the root [`requirements.txt`](../../requirements.txt).)

## What this service does NOT do

- No authentication / sessions / users.
- No image cleanup — uploads accumulate in `fastApi-app/images/` (and `tmp/` for debug overlays).
- No background workers; processing is synchronous within the request.
- No streaming; `/images/click` returns the full base64 payload in one JSON response.
- No options pass-through to the pipeline yet (the `options` field on `ClickRequest` is parsed but not currently used inside `ObjectRemover.remove_object` — see [core-image-processing.md](core-image-processing.md)).
