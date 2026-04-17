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