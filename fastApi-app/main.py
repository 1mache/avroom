from __future__ import annotations

from fastapi import FastAPI

from api.routes import router as images_router

app = FastAPI(
    title="Image Processing Service",
    version="0.1.0",
    description=(
        "MVP FastAPI microservice for image upload and click-based operations. "
        "Processing logic is stubbed and can be filled in later."
    ),
)


@app.get("/")
async def read_root() -> dict[str, str]:
    """Health/info endpoint for the image processing service."""

    return {"status": "ok", "service": "image-processing"}


app.include_router(images_router)