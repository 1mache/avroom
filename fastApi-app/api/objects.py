from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from avroom_object_removal.ai_engines.reconstruction_3d import (
    Reconstruction3DFacade,
    ReconstructionQuality,
)

from core.object_storage import object_glb_path, resolve_object_cutout_path, resolve_object_glb_path
from settings import get_3d_storage_dir, get_image_storage_dir

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
    object_id: Annotated[
        int,
        Field(ge=0, description="Zero-based object id within the session to generate 3D from."),
    ] = 0


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
    logger.info(
        "test-3d called: uid=%s object_id=%d debug_mode=%s",
        request.uid,
        request.object_id,
        _DEBUG_MODE,
    )

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

    cutout_image_path = resolve_object_cutout_path(
        get_image_storage_dir(), request.uid, request.object_id
    )
    if not cutout_image_path.exists():
        logger.error(
            "Cutout image not found: uid=%s object_id=%d path=%s",
            request.uid,
            request.object_id,
            cutout_image_path,
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"Cutout image not found at {cutout_image_path}. "
                f"Run object removal first so the cutout for object {request.object_id} exists."
            ),
        )

    try:
        glb_bytes = _get_facade().generate(
            cutout_image_path,
            quality=ReconstructionQuality.HIGH,
            output="bytes",
        )
    except Exception as exc:
        logger.exception("3D generation failed")
        raise HTTPException(status_code=500, detail=f"3D generation failed: {exc}") from exc

    assert isinstance(glb_bytes, bytes)

    glb_dir = get_3d_storage_dir()
    glb_dir.mkdir(parents=True, exist_ok=True)
    glb_path = object_glb_path(glb_dir, request.uid, request.object_id)
    glb_path.write_bytes(glb_bytes)
    logger.info(
        "test-3d complete: uid=%s object_id=%d glb_bytes=%d saved=%s",
        request.uid,
        request.object_id,
        len(glb_bytes),
        glb_path,
    )

    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'inline; filename="{request.uid}_{request.object_id}.glb"'},
    )


@router.get("/{uid}/{object_id}")
async def get_3d_model_by_object(uid: str, object_id: int) -> FileResponse:
    """Serve the cached GLB 3D model for a specific object within a session."""
    logger.info("3D model by object requested: uid=%s object_id=%d", uid, object_id)
    path = resolve_object_glb_path(get_3d_storage_dir(), uid, object_id)
    if not path.exists():
        logger.warning(
            "3D model not found: uid=%s object_id=%d path=%s", uid, object_id, path
        )
        raise HTTPException(status_code=404, detail="3D model not found")
    logger.info("3D model by object served: uid=%s object_id=%d path=%s", uid, object_id, path)
    return FileResponse(
        path,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'inline; filename="{uid}_{object_id}.glb"'},
    )


@router.get("/{uid}")
async def get_3d_model(uid: str) -> FileResponse:
    """Serve the cached GLB 3D model for the given UID.

    Legacy fallback: serves object id 0's model (or the legacy ``{uid}.glb``
    file for sessions created before the numbered-object scheme).
    """
    logger.info("3D model requested: uid=%s", uid)
    path = resolve_object_glb_path(get_3d_storage_dir(), uid, 0)
    if not path.exists():
        logger.warning("3D model not found: uid=%s path=%s", uid, path)
        raise HTTPException(status_code=404, detail="3D model not found")
    logger.info("3D model served: uid=%s path=%s", uid, path)
    return FileResponse(
        path,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'inline; filename="{uid}.glb"'},
    )
