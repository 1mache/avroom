from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from avroom_object_removal.ai_engines.reconstruction_3d import (
    Reconstruction3DFacade,
    ReconstructionQuality,
)

from settings import get_image_storage_dir

router = APIRouter(prefix="/objects", tags=["objects"])
logger = logging.getLogger(__name__)

_DEBUG_MODE = False
_DEBUG_MODEL_PATH = Path(__file__).resolve().parent.parent / "res" / "test" / "debug_toilet.glb"

_facade: Reconstruction3DFacade | None = None


class Test3DRequest(BaseModel):
    """JSON body for POST /objects/test-3d."""

    uid: Annotated[
        str,
        Field(min_length=1, description="Image uid used to locate the cutout PNG."),
    ]


def _get_facade() -> Reconstruction3DFacade:
    global _facade
    if _facade is None:
        _facade = Reconstruction3DFacade()
    return _facade


@router.post("/test-3d")
async def generate_test_3d(request: Test3DRequest) -> Response:
    """Generate a GLB 3D model from the stored cutout for the given uid.

    In non-debug mode the cutout is read from the image storage directory as
    ``{uid}_cutout.png`` (same layout as the image click endpoint).

    Returns raw GLB bytes (model/gltf-binary). Intended for Three.js consumption
    via GLTFLoader.load() or GLTFLoader.parse().
    """
    logger.info("test-3d called: uid=%s debug_mode=%s", request.uid, _DEBUG_MODE)

    if _DEBUG_MODE:
        if not _DEBUG_MODEL_PATH.exists():
            logger.error("Debug model not found: %s", _DEBUG_MODEL_PATH)
            raise HTTPException(
                status_code=404,
                detail=f"Debug model not found at {_DEBUG_MODEL_PATH}. "
                "Place debug_toilet.glb at fastApi-app/res/test/debug_toilet.glb.",
            )
        logger.info("test-3d debug shortcut: returning %s", _DEBUG_MODEL_PATH)
        return Response(
            content=_DEBUG_MODEL_PATH.read_bytes(),
            media_type="model/gltf-binary",
            headers={"Content-Disposition": "inline; filename=debug_toilet.glb"},
        )

    cutout_image_path = get_image_storage_dir() / f"{request.uid}_cutout.png"
    if not cutout_image_path.exists():
        logger.error("Cutout image not found: %s", cutout_image_path)
        raise HTTPException(
            status_code=404,
            detail=(
                f"Cutout image not found at {cutout_image_path}. "
                f"Run object removal first so {request.uid}_cutout.png exists."
            ),
        )

    try:
        glb_bytes = _get_facade().generate(
            cutout_image_path,
            quality=ReconstructionQuality.FAST,
            output="bytes",
        )
    except Exception as exc:
        logger.exception("3D generation failed")
        raise HTTPException(status_code=500, detail=f"3D generation failed: {exc}") from exc

    assert isinstance(glb_bytes, bytes)
    logger.info("test-3d complete: uid=%s glb_bytes=%d", request.uid, len(glb_bytes))

    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'inline; filename="{request.uid}.glb"'},
    )
