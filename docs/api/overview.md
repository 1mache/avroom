# API Service Overview

**Directory:** `fastApi-app/`

## Purpose

The FastAPI service is the HTTP layer between the React frontend and the CV/ML pipeline. It exposes two endpoints — image upload and click processing — and delegates all actual image work to the `TestModules` pipeline.

## Application Factory

**File:** `fastApi-app/main.py`

```python
app = FastAPI(
    title="Image Processing Service",
    version="0.1.0",
)
```

### CORS

CORS is configured to allow the Vite dev server:

```python
allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"]
allow_methods=["*"]
allow_headers=["*"]
allow_credentials=True
```

Production deployments should restrict origins appropriately.

### Health Endpoint

`GET /` returns:
```json
{ "status": "ok", "service": "image-processing" }
```

## Starting the Server

From the `fastApi-app/` directory (with the venv active):

```powershell
fastapi dev main.py
```

This starts Uvicorn in development mode with hot reload on `http://127.0.0.1:8000`.

## Configuration

**File:** `fastApi-app/settings.py`

| Setting | Default | Description |
|---|---|---|
| `IMAGE_STORAGE_DIR` | `fastApi-app/images/` | Where uploaded images are saved |

`get_image_storage_dir()` returns a `pathlib.Path` for the storage directory.

## Sub-documentation

- [`endpoints.md`](endpoints.md) — upload and click endpoint contracts
- [`image-processing.md`](image-processing.md) — how the API bridges to the pipeline
- [`schemas.md`](schemas.md) — Pydantic request/response models
