from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.routes import router as images_router
from api.model_3d import router as model_3d_router
from logging_config import setup_logging

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
    logger.info("Image processing service started")
    yield
    # shutdown
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
app.include_router(model_3d_router)
logger.info("FastAPI app initialized")
