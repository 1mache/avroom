from __future__ import annotations

import functools
import logging
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from PIL import Image

from ..reconstruction_3d_strategy import OutputMode, Reconstruction3DStrategy
from ..reconstruction_glb_writer import write_output
from ..reconstruction_image_input import to_pil_rgba
from ..reconstruction_quality import ReconstructionQuality

logger = logging.getLogger(__name__)


def _mc_resolution_for_quality(quality: ReconstructionQuality) -> int:
    """Map quality preset to TripoSR marching-cubes resolution (coarse→fine)."""

    if quality is ReconstructionQuality.FAST:
        return 192
    if quality is ReconstructionQuality.BALANCED:
        return 256
    return 320


def _ensure_triposr_import_path() -> None:
    """Put the vendored ``tsr`` package (TripoSR) on ``sys.path``.

    Hub ``config.yaml`` resolves model classes as ``tsr.*``; the parent of the
    ``tsr`` package directory must therefore appear on the import path.
    """

    root = Path(__file__).resolve().parent.parent / "_backends" / "triposr"
    tsr_dir = root / "tsr"
    if not tsr_dir.is_dir():
        raise RuntimeError(
            f"Vendored TripoSR (``tsr``) not found at {tsr_dir}. "
            "Reinstall the ``avroom-object-removal`` package."
        )
    insert = str(root)
    if insert not in sys.path:
        sys.path.insert(0, insert)


@functools.lru_cache(maxsize=8)
def _load_tsr_model(
    pretrained_model_name_or_path: str,
    config_name: str,
    weight_name: str,
    chunk_size: int,
    device: str,
) -> Any:
    """Load ``TSR`` once per (checkpoint, device, chunk_size) tuple."""

    _ensure_triposr_import_path()

    try:
        import torch
        from tsr.system import TSR
    except ModuleNotFoundError as exc:
        logger.error("TripoSR import failed: %s", exc)
        raise RuntimeError(
            "TripoSR local inference requires PyTorch, vendored ``tsr``, "
            "``torchmcubes``, ``omegaconf``, and ``einops``. "
            "Install TestModules dependencies (see requirements.txt)."
        ) from exc

    logger.info(
        "Lazy-loading TripoSR TSR from %s onto %s",
        pretrained_model_name_or_path,
        device,
    )
    model = TSR.from_pretrained(
        pretrained_model_name_or_path,
        config_name=config_name,
        weight_name=weight_name,
    )
    model.renderer.set_chunk_size(chunk_size)
    model.to(device)
    model.eval()
    return model


class Triposr3DGenerationError(RuntimeError):
    """Raised when local TripoSR inference or GLB export fails."""


class TriposrReconstructionStrategy(Reconstruction3DStrategy):
    """Image-to-GLB using TripoSR (local PyTorch; HF weights on first use).

    Vendored upstream code lives under
    ``_backends/triposr/tsr`` (MIT; see ``LICENSE.TripoSR`` there). Default
    weights are ``stabilityai/TripoSR`` from Hugging Face Hub.

    Expect roughly **6 GB VRAM** for a single forward pass at default settings
    on CUDA (per upstream TripoSR README); falls back to CPU if no GPU.

    ``seed`` is applied to PyTorch / NumPy RNGs before inference.
    """

    def __init__(
        self,
        pretrained_model_name_or_path: str = "stabilityai/TripoSR",
        *,
        config_name: str = "config.yaml",
        weight_name: str = "model.ckpt",
        chunk_size: int = 8192,
        remove_background: bool = False,
        foreground_ratio: float = 0.85,
        device: str | None = None,
    ) -> None:
        self._pretrained = pretrained_model_name_or_path
        self._config_name = config_name
        self._weight_name = weight_name
        self._chunk_size = chunk_size
        self._remove_background = remove_background
        self._foreground_ratio = foreground_ratio
        if device is None:
            try:
                import torch

                self._device = "cuda:0" if torch.cuda.is_available() else "cpu"
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "TripoSR requires ``torch``. Install TestModules dependencies."
                ) from exc
        else:
            self._device = device

    def _preprocess(self, pil_rgba: Image.Image) -> Image.Image:
        """Align with TripoSR ``run.py`` / ``gradio_app.py`` preprocessing."""

        _ensure_triposr_import_path()

        if self._remove_background:
            import rembg
            from tsr.utils import remove_background as tsr_remove_bg, resize_foreground

            session = rembg.new_session()
            no_bg = tsr_remove_bg(pil_rgba.convert("RGB"), session)
            resized = resize_foreground(no_bg, self._foreground_ratio)
            arr = np.array(resized).astype(np.float32) / 255.0
            rgb = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5
            return Image.fromarray((rgb * 255.0).astype(np.uint8))

        if pil_rgba.mode == "RGBA":
            arr = np.array(pil_rgba).astype(np.float32) / 255.0
            rgb = arr[:, :, :3] * arr[:, :, 3:4] + (1 - arr[:, :, 3:4]) * 0.5
            return Image.fromarray((rgb * 255.0).astype(np.uint8))
        return pil_rgba.convert("RGB")

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

        try:
            import torch
        except ModuleNotFoundError as exc:
            logger.error("torch not installed")
            raise RuntimeError(
                "TripoSR requires ``torch``. Install TestModules dependencies."
            ) from exc

        mc_resolution = _mc_resolution_for_quality(quality)

        logger.info(
            "generate called: model=%s quality=%s mc_resolution=%d seed=%s device=%s output=%s",
            self._pretrained,
            quality.value,
            mc_resolution,
            seed,
            self._device,
            output,
        )

        torch.manual_seed(seed)
        np.random.seed(int(seed) % (2**32))

        pil_rgba = to_pil_rgba(image)
        logger.debug("Input image as RGBA: size=%s", pil_rgba.size)

        try:
            processed = self._preprocess(pil_rgba)
        except Exception as exc:
            logger.error("TripoSR preprocess failed: %s", exc)
            raise Triposr3DGenerationError(f"TripoSR preprocessing failed: {exc}") from exc

        model = _load_tsr_model(
            self._pretrained,
            self._config_name,
            self._weight_name,
            self._chunk_size,
            self._device,
        )

        with tempfile.TemporaryDirectory(prefix="triposr_work_") as work_dir:
            work = Path(work_dir)
            glb_path = work / f"triposr_{uuid.uuid4().hex}.glb"

            try:
                with torch.inference_mode():
                    scene_codes = model([processed], device=self._device)
                    meshes = model.extract_mesh(
                        scene_codes,
                        True,
                        resolution=mc_resolution,
                    )
                mesh = meshes[0]
            except Triposr3DGenerationError:
                raise
            except Exception as exc:
                logger.error("TripoSR inference failed: %s", exc)
                raise Triposr3DGenerationError(
                    f"TripoSR inference failed for {self._pretrained}: {exc}"
                ) from exc

            try:
                mesh.export(str(glb_path), file_type="glb")
            except Exception as exc:
                logger.error("TripoSR GLB export failed: %s", exc)
                raise Triposr3DGenerationError(
                    f"Failed to export TripoSR mesh to GLB: {exc}"
                ) from exc

            logger.debug("Exported GLB at %s", glb_path)
            result = write_output(glb_path, output, output_path)

        if output == "bytes":
            assert isinstance(result, bytes)
            logger.info(
                "generate complete: quality=%s glb_bytes=%d",
                quality.value,
                len(result),
            )
        else:
            logger.info("generate complete: quality=%s output=%s", quality.value, str(result))

        return result
