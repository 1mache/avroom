from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as images_router
from api.objects import router as objects_router
from logging_config import setup_logging


setup_logging()
logger = logging.getLogger(__name__)


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
app.include_router(objects_router)
logger.info("FastAPI app initialized")


@app.on_event("startup")
async def _on_startup() -> None:
    """Log service startup so the operator can confirm the app booted."""

    logger.info("Image processing service started")


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """Log service shutdown so the operator can confirm a clean exit."""

    logger.info("Image processing service shutting down")
