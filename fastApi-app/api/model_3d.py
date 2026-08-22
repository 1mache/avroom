from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from core.auth.identity import current_user_id
from core.object_storage import resolve_object_cutout_path, resolve_object_glb_path
from core.repositories.job_repo import create_job
from schemas.jobs import Generate3DJobRequest, JobSubmitResponse
from settings import get_3d_storage_dir, get_image_storage_dir

router = APIRouter(prefix="/3d", tags=["3d"])
logger = logging.getLogger(__name__)

_DEBUG_MODE = False
_DEBUG_MODEL_PATH = Path(__file__).resolve().parent.parent / "res" / "test" / "debug_toilet.glb"


@router.post("/test-3d", response_model=JobSubmitResponse, status_code=202)
async def generate_test_3d(
    request: Generate3DJobRequest, user_id: str = Depends(current_user_id)
) -> JobSubmitResponse:
    """Queue GLB generation from the stored cutout for the given uid and return immediately.

    The cutout is read from the image storage directory using the standard
    per-object naming (``{uid}_{object_id}_cutout.png``). Poll
    `GET /jobs/{job_id}` for completion, then `GET /3d/{uid}/{object_id}` for
    the GLB itself.
    """
    logger.info(
        "3D generation queued: uid=%s object_id=%d debug_mode=%s user_id=%s",
        request.uid,
        request.object_id,
        _DEBUG_MODE,
        user_id,
    )

    if _DEBUG_MODE:
        if not _DEBUG_MODEL_PATH.exists():
            logger.error("Debug model not found: %s", _DEBUG_MODEL_PATH)
            raise HTTPException(
                status_code=404,
                detail=f"Debug model not found at {_DEBUG_MODEL_PATH}. "
                "Place debug_toilet.glb at fastApi-app/res/test/debug_toilet.glb.",
            )
        glb_dir = get_3d_storage_dir()
        glb_dir.mkdir(parents=True, exist_ok=True)
        (glb_dir / f"{request.uid}_{request.object_id}.glb").write_bytes(_DEBUG_MODEL_PATH.read_bytes())
        job = create_job(user_id, request.uid, "generate_3d", {"object_id": request.object_id})
        return JobSubmitResponse(job_id=job.id)

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

    job = create_job(user_id, request.uid, "generate_3d", {"object_id": request.object_id})
    return JobSubmitResponse(job_id=job.id)


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
