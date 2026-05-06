from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from avroom_object_removal.ai_engines.reconstruction_3d import (
    Reconstruction3DFacade,
    ReconstructionQuality,
)

router = APIRouter(prefix="/objects", tags=["objects"])
logger = logging.getLogger(__name__)

_DEBUG_MODE = True
_TEST_IMAGE_PATH = Path(__file__).resolve().parent.parent / "tmp" / "3d" / "toilet.png"
_DEBUG_MODEL_PATH = Path(__file__).resolve().parent.parent / "tmp" / "3d" / "debug_toilet.glb"

_facade: Reconstruction3DFacade | None = None


def _get_facade() -> Reconstruction3DFacade:
    global _facade
    if _facade is None:
        _facade = Reconstruction3DFacade()
    return _facade


@router.post("/test-3d")
async def generate_test_3d() -> Response:
    """Generate a GLB 3D model from tmp/3d/toilet.png.

    Returns raw GLB bytes (model/gltf-binary). Intended for Three.js consumption
    via GLTFLoader.load() or GLTFLoader.parse().
    """
    logger.info("test-3d called: debug_mode=%s", _DEBUG_MODE)

    if _DEBUG_MODE:
        if not _DEBUG_MODEL_PATH.exists():
            logger.error("Debug model not found: %s", _DEBUG_MODEL_PATH)
            raise HTTPException(
                status_code=404,
                detail=f"Debug model not found at {_DEBUG_MODEL_PATH}. "
                "Place debug_toilet.glb at fastApi-app/tmp/3d/debug_toilet.glb.",
            )
        logger.info("test-3d debug shortcut: returning %s", _DEBUG_MODEL_PATH)
        return Response(
            content=_DEBUG_MODEL_PATH.read_bytes(),
            media_type="model/gltf-binary",
            headers={"Content-Disposition": "inline; filename=debug_toilet.glb"},
        )

    if not _TEST_IMAGE_PATH.exists():
        logger.error("Test image not found: %s", _TEST_IMAGE_PATH)
        raise HTTPException(
            status_code=404,
            detail=f"Test image not found at {_TEST_IMAGE_PATH}. "
            "Place toilet.png at fastApi-app/tmp/3d/toilet.png.",
        )

    try:
        glb_bytes = _get_facade().generate(
            _TEST_IMAGE_PATH,
            quality=ReconstructionQuality.FAST,
            output="bytes",
        )
    except Exception as exc:
        logger.exception("3D generation failed")
        raise HTTPException(status_code=500, detail=f"3D generation failed: {exc}") from exc

    assert isinstance(glb_bytes, bytes)
    logger.info("test-3d complete: glb_bytes=%d", len(glb_bytes))

    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": "inline; filename=toilet.glb"},
    )
