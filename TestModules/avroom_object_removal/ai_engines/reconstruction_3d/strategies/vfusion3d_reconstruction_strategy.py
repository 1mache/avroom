from __future__ import annotations

import functools
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
import torch
import trimesh
from PIL import Image

from ..reconstruction_3d_strategy import OutputMode, Reconstruction3DStrategy
from ..reconstruction_glb_writer import write_output
from ..reconstruction_image_input import to_pil_rgba
from ..reconstruction_quality import ReconstructionQuality

logger = logging.getLogger(__name__)

DEFAULT_MODEL_REPO = "jadechoghari/vfusion3d"

# Hub model writes this fixed filename in the current working directory when
# ``export_mesh=True`` (see ``modeling.py`` on the HF repo).
_VFUSION_MESH_BASENAME = "awesome_mesh.obj"


def _mesh_size_for_quality(quality: ReconstructionQuality) -> int:
    if quality is ReconstructionQuality.FAST:
        return 288
    if quality is ReconstructionQuality.BALANCED:
        return 384
    return 512


def _pil_rgba_to_rgb_on_white(pil_rgba: Image.Image) -> Image.Image:
    """Flatten alpha onto white for processors that expect a photo-like RGB crop."""

    rgba = pil_rgba.convert("RGBA")
    background = Image.new("RGB", rgba.size, (255, 255, 255))
    background.paste(rgba, mask=rgba.split()[-1])
    return background


@functools.lru_cache(maxsize=1)
def _get_vfusion_bundle(model_repo_id: str) -> tuple[Any, Any, torch.device]:
    """Load HF VFusion3D weights, processor, and place the model on the active device once."""

    try:
        from transformers import AutoModel, AutoProcessor
    except ModuleNotFoundError as exc:
        logger.error("transformers not installed")
        raise RuntimeError(
            "Missing dependency `transformers`. Install TestModules package dependencies."
        ) from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(
        "Lazy-loading VFusion3D from %s onto %s",
        model_repo_id,
        device,
    )

    try:
        model = AutoModel.from_pretrained(
            model_repo_id,
            trust_remote_code=True,
        )
        processor = AutoProcessor.from_pretrained(
            model_repo_id,
            trust_remote_code=True,
        )
    except ModuleNotFoundError as exc:
        logger.error("VFusion3D hub code import failed: %s", exc)
        raise Vfusion3dReconstructionError(
            "VFusion3D requires extra packages used by its Hugging Face processor "
            "(e.g. `rembg`, `kiui`, `torchvision`). Install TestModules "
            "dependencies or see the model card: "
            "https://huggingface.co/jadechoghari/vfusion3d"
        ) from exc

    model = model.to(device)
    model.eval()
    return model, processor, device


class Vfusion3dReconstructionError(RuntimeError):
    """Raised when VFusion3D inference or GLB export fails."""


class Vfusion3dReconstructionStrategy(Reconstruction3DStrategy):
    """Image-to-GLB using VFusion3D (HF ``transformers`` + remote modeling code).

    Default checkpoint ``jadechoghari/vfusion3d`` is CC BY-NC 2.0 (non-commercial).
    The hub ``AutoProcessor`` runs background removal and centering (``rembg`` /
    ``kiui``) before inference.

    :class:`~avroom_object_removal.ai_engines.reconstruction_3d.reconstruction_quality.GenerationParams`
    presets are Trellis-specific; for this strategy only ``mesh_size`` (marching-cubes
    grid resolution) is derived from
    :class:`~avroom_object_removal.ai_engines.reconstruction_3d.reconstruction_quality.ReconstructionQuality`.
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

        torch.manual_seed(seed)
        np.random.seed(int(seed) % (2**32))

        mesh_size = _mesh_size_for_quality(quality)
        logger.info(
            "generate called: model=%s quality=%s mesh_size=%d seed=%d output=%s",
            self._model_repo_id,
            quality.value,
            mesh_size,
            seed,
            output,
        )

        pil_rgba = to_pil_rgba(image)
        logger.debug("Input image as RGBA: size=%s", pil_rgba.size)
        pil_rgb = _pil_rgba_to_rgb_on_white(pil_rgba)
        logger.debug("Prepared RGB (white background): size=%s", pil_rgb.size)

        model, processor, device = _get_vfusion_bundle(self._model_repo_id)

        stem = f"vfusion3d_{uuid.uuid4().hex}"
        old_cwd = Path.cwd()

        with tempfile.TemporaryDirectory(prefix="vfusion3d_work_") as work_dir:
            work = Path(work_dir)
            mesh_rel: str | os.PathLike[str] | None = None
            try:
                os.chdir(work)
                processed_image, source_camera = processor(pil_rgb)
                processed_image = processed_image.to(device)
                source_camera = source_camera.to(device)
                logger.debug(
                    "Processor output shapes: image=%s camera=%s",
                    tuple(processed_image.shape),
                    tuple(source_camera.shape),
                )

                with torch.inference_mode():
                    _planes, mesh_rel = model(
                        processed_image,
                        source_camera,
                        export_mesh=True,
                        mesh_size=mesh_size,
                    )
            except Vfusion3dReconstructionError:
                raise
            except Exception as exc:
                logger.error("VFusion3D inference failed: %s", exc)
                raise Vfusion3dReconstructionError(
                    f"VFusion3D inference failed for {self._model_repo_id}: {exc}"
                ) from exc
            finally:
                os.chdir(old_cwd)

            if mesh_rel is not None:
                returned = Path(os.fspath(mesh_rel))
                mesh_path = returned if returned.is_absolute() else work / returned
            else:
                mesh_path = work / _VFUSION_MESH_BASENAME

            if not mesh_path.is_file():
                mesh_path = work / _VFUSION_MESH_BASENAME

            if not mesh_path.is_file():
                raise Vfusion3dReconstructionError(
                    f"Expected mesh file under {work} after inference, "
                    f"got mesh_path={mesh_rel!r}."
                )

            logger.debug("Loaded mesh from %s", mesh_path)

            try:
                loaded = trimesh.load(str(mesh_path), force="mesh")
            except Exception as exc:
                logger.error("trimesh load failed: %s", exc)
                raise Vfusion3dReconstructionError(
                    f"Failed to load VFusion3D mesh from {mesh_path}: {exc}"
                ) from exc

            if isinstance(loaded, trimesh.Scene):
                geoms = list(loaded.geometry.values())
                if not geoms:
                    raise Vfusion3dReconstructionError(
                        "VFusion3D produced an empty mesh scene."
                    )
                mesh = (
                    trimesh.util.concatenate(geoms)
                    if len(geoms) > 1
                    else geoms[0]
                )
            else:
                mesh = loaded

            glb_path = work / f"{stem}.glb"
            try:
                mesh.export(str(glb_path), file_type="glb")
            except Exception as exc:
                logger.error("GLB export failed: %s", exc)
                raise Vfusion3dReconstructionError(
                    f"Failed to export GLB from VFusion3D mesh: {exc}"
                ) from exc

            logger.debug("Exported intermediate GLB at %s", glb_path)
            result = write_output(glb_path, output, output_path)

        if output == "bytes":
            assert isinstance(result, bytes)
            logger.info("generate complete: glb_bytes=%d", len(result))
        else:
            logger.info("generate complete: output=%s", str(result))
        return result
