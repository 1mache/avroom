from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from api.auth import router as auth_router
from api.routes import router as images_router
from api.sessions import router as sessions_router
from api.object_views import router as object_views_router
from api.model_3d import router as model_3d_router
from api.novel_view import router as novel_view_router
from api.debug_vision import router as debug_vision_router
from api.jobs import router as jobs_router
from core.auth.jwt_backend import ensure_configured as ensure_jwt_configured
from core.inference_pool.client import init_inference_client, shutdown_inference_client
from core.inference_pool.pool import InferencePool
from core.jobs.dispatcher import start_dispatcher, stop_dispatcher
from core.repositories.job_repo import mark_running_orphans_failed
from logging_config import setup_logging
from settings import get_auth_mode, get_cors_allow_origins, get_inference_worker_count

# Load fastApi-app/.env (gitignored) into os.environ before anything else runs,
# so HF_TOKEN is available when the 3D reconstruction strategies are lazily
# instantiated on first use (see hunyuan3d2_reconstruction_strategy.py /
# trellis_reconstruction_strategy.py).
load_dotenv()

setup_logging()
logger = logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    if get_auth_mode() == "jwt":
        # Fail loudly here, not on the first login request -- a missing
        # secret would otherwise 500 mid-request instead of refusing to boot.
        ensure_jwt_configured()
    pool: InferencePool | None = None
    worker_count = get_inference_worker_count()
    if worker_count > 0:
        pool = InferencePool.start()
    init_inference_client(pool)
    mark_running_orphans_failed()
    start_dispatcher()
    logger.info("Image processing service started")
    yield
    # shutdown
    stop_dispatcher()
    shutdown_inference_client()
    logger.info("Image processing service shutting down")

app = FastAPI(
    title="Image Processing Service",
    version="0.1.0",
    description=(
        "MVP FastAPI microservice for image upload and click-based operations. "
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Env-driven via CORS_ALLOW_ORIGINS (comma-separated); defaults to the two
    # local Vite dev origins so no env var is needed to run locally.
    allow_origins=get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # allow_headers only covers request headers; response headers beyond the
    # CORS-safelisted set (Content-Type etc.) need explicit exposure or
    # browser JS reads them as null. Both custom headers set by
    # api/debug_vision.py need this.
    expose_headers=["X-Mask-Count", "X-Elapsed-Ms"],
)


@app.get("/healthz")
async def read_root() -> dict[str, str]:
    """Health/info endpoint for the image processing service.

    Served at `/healthz` rather than `/` because `/` is claimed by the built
    frontend's index.html when a SPA build is mounted (see the StaticFiles
    mount at the bottom of this file). Routes registered here always win over
    that mount, so keeping this on `/` would shadow the app itself.
    """

    return {"status": "ok", "service": "image-processing"}


app.include_router(images_router)
app.include_router(sessions_router)
app.include_router(object_views_router)
app.include_router(model_3d_router)
app.include_router(novel_view_router)
app.include_router(debug_vision_router)
app.include_router(jobs_router)
app.include_router(auth_router)

# Serve the built React SPA from this same app, when a build is present.
#
# This is what lets the deployed container answer on one port with no nginx
# and no CORS: the SPA is built with VITE_API_BASE_URL="" (see
# fastApi-app/Dockerfile), so its fetches are relative and resolve back to
# whichever origin served the page.
#
# Mounted LAST on purpose. Starlette matches routes in registration order, so
# every router above still wins for /images, /3d, /jobs and /debug; the mount
# only catches what is left (/, /assets/*, /avroom.png). Those namespaces do
# not collide with Vite's output.
#
# Absent in local development (no `npm run build` output), where the Vite dev
# server on :5173 serves the SPA instead - so the mount is skipped rather than
# raising on a missing directory.
_SPA_DIR = Path(__file__).resolve().parent.parent / "react-front" / "dist"
if _SPA_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_SPA_DIR, html=True), name="frontend")
    logger.info("Serving built frontend from %s", _SPA_DIR)
else:
    logger.info("No frontend build at %s; serving API only", _SPA_DIR)

logger.info("FastAPI app initialized")
