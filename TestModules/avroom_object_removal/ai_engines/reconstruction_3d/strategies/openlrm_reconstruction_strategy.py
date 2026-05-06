from __future__ import annotations

import functools
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
import torch
import trimesh
from PIL import Image  # type: ignore[import-untyped]

from ..reconstruction_3d_strategy import OutputMode, Reconstruction3DStrategy
from ..reconstruction_glb_writer import write_output
from ..reconstruction_image_input import to_pil_rgba
from ..reconstruction_quality import ReconstructionQuality

logger = logging.getLogger(__name__)

DEFAULT_MODEL_REPO = "zxhezexin/openlrm-small-obj-1.0"


def _normalize_model_short_name(model_repo_id: str) -> str:
    """Return v1.0 ``LRMInferrer`` model name (HF repo is ``zxhezexin/<name>``)."""

    s = model_repo_id.strip()
    if "/" not in s:
        return s
    org, name = s.split("/", 1)
    if org != "zxhezexin":
        raise ValueError(
            "OpenLrmReconstructionStrategy only supports Hugging Face repos under "
            f"organization 'zxhezexin', got {model_repo_id!r}."
        )
    return name


@functools.lru_cache(maxsize=1)
def _get_lrm_inferrer(model_short_name: str) -> Any:
    """Lazy-load OpenLRM weights and build ``LRMInferrer`` once per model key."""

    from avroom_object_removal.ai_engines.reconstruction_3d._backends.openlrm_v10.lrm.inferrer import (  # type: ignore[import-not-found]
        LRMInferrer,
    )

    logger.info("Lazy-loading OpenLRM inferrer for checkpoint %s", model_short_name)
    return LRMInferrer(model_short_name)


def _mesh_size_for_quality(quality: ReconstructionQuality) -> int:
    if quality is ReconstructionQuality.FAST:
        return 288
    if quality is ReconstructionQuality.BALANCED:
        return 384
    return 512


class OpenLrmReconstructionError(RuntimeError):
    """Raised when OpenLRM inference or GLB export fails."""


class OpenLrmReconstructionStrategy(Reconstruction3DStrategy):
    """Image-to-GLB using OpenLRM v1.0 (local PyTorch; HF checkpoint download on first use).

    Default checkpoint ``zxhezexin/openlrm-small-obj-1.0`` is licensed CC BY-NC 4.0
    (non-commercial). See the Hugging Face model card.

    :class:`~avroom_object_removal.ai_engines.reconstruction_3d.reconstruction_quality.GenerationParams`
    presets are Trellis-specific; for this strategy only ``mesh_size`` is derived
    from :class:`~avroom_object_removal.ai_engines.reconstruction_3d.reconstruction_quality.ReconstructionQuality`.
    """

    def __init__(self, model_repo_id: str = DEFAULT_MODEL_REPO) -> None:
        self._model_repo_id = model_repo_id

    def generate(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        quality: ReconstructionQuality = ReconstructionQuality.FAST,
        output: OutputMode = "bytes",
        output_path: Path | None = None,
        seed: int = 0,
    ) -> bytes | Path | BinaryIO:
        if output not in ("bytes", "path", "file"):
            raise ValueError(f"output must be 'bytes', 'path', or 'file', got {output!r}.")

        pil_image = to_pil_rgba(image)
        logger.debug("Input image as RGBA: size=%s", pil_image.size)

        torch.manual_seed(seed)
        np.random.seed(int(seed) % (2**32))

        short_name = _normalize_model_short_name(self._model_repo_id)
        inferrer = _get_lrm_inferrer(short_name)
        mesh_size = _mesh_size_for_quality(quality)

        logger.info(
            "generate called: model=%s quality=%s mesh_size=%d seed=%d output=%s",
            self._model_repo_id,
            quality.value,
            mesh_size,
            seed,
            output,
        )

        stem = f"openlrm_{uuid.uuid4().hex}"

        with tempfile.TemporaryDirectory(prefix="openlrm_work_") as work_dir:
            work = Path(work_dir)
            src_png = work / f"{stem}.png"
            pil_image.save(src_png, format="PNG")
            logger.debug("Wrote OpenLRM input PNG: %s", src_png)

            try:
                inferrer.infer(
                    source_image=str(src_png),
                    dump_path=str(work),
                    source_size=-1,
                    render_size=-1,
                    mesh_size=mesh_size,
                    export_video=False,
                    export_mesh=True,
                )
            except Exception as exc:
                logger.error("OpenLRM infer failed: %s", exc)
                raise OpenLrmReconstructionError(
                    f"OpenLRM inference failed for {self._model_repo_id}: {exc}"
                ) from exc

            ply_path = work / f"{stem}.ply"
            if not ply_path.is_file():
                raise OpenLrmReconstructionError(
                    f"Expected mesh file {ply_path} after inference, but it is missing."
                )

            loaded = trimesh.load(str(ply_path), force="mesh")
            if isinstance(loaded, trimesh.Scene):
                geoms = list(loaded.geometry.values())
                if not geoms:
                    raise OpenLrmReconstructionError("OpenLRM produced an empty mesh scene.")
                mesh = (
                    trimesh.util.concatenate(geoms)
                    if len(geoms) > 1
                    else geoms[0]
                )
            else:
                mesh = loaded

            glb_path = work / f"{stem}.glb"
            mesh.export(str(glb_path), file_type="glb")
            logger.debug("Exported intermediate GLB at %s", glb_path)

            result = write_output(glb_path, output, output_path)

        if output == "bytes":
            assert isinstance(result, bytes)
            logger.info("generate complete: glb_bytes=%d", len(result))
        else:
            logger.info("generate complete: output=%s", str(result))
        return result
