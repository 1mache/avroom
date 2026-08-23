from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.routes import router as images_router
from api.model_3d import router as model_3d_router
from api.novel_view import router as novel_view_router
from api.debug_vision import router as debug_vision_router
from api.jobs import router as jobs_router
from core.inference_pool.client import init_inference_client, shutdown_inference_client
from core.inference_pool.pool import InferencePool
from core.jobs.dispatcher import start_dispatcher, stop_dispatcher
from core.repositories.job_repo import mark_running_orphans_failed
from logging_config import setup_logging
from settings import get_cors_allow_origins, get_inference_worker_count

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


@app.get("/")
async def read_root() -> dict[str, str]:
    """Health/info endpoint for the image processing service."""

    return {"status": "ok", "service": "image-processing"}


app.include_router(images_router)
app.include_router(model_3d_router)
app.include_router(novel_view_router)
app.include_router(debug_vision_router)
app.include_router(jobs_router)
logger.info("FastAPI app initialized")
