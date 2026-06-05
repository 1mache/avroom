from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from PIL import Image

from ..reconstruction_3d_strategy import OutputMode, Reconstruction3DStrategy
from ..reconstruction_glb_writer import write_output
from ..reconstruction_image_input import to_pil_rgba
from ..reconstruction_quality import ReconstructionQuality

logger = logging.getLogger(__name__)

# Quality preset → (num_inference_steps, octree_resolution)
_QUALITY_PARAMS: dict[ReconstructionQuality, tuple[int, int]] = {
    ReconstructionQuality.FAST: (5, 128),
    ReconstructionQuality.BALANCED: (20, 256),
    ReconstructionQuality.HIGH: (50, 384),
}

# num_chunks controls how many surface points are evaluated in one batch during
# voxel decoding. The Space default is 8 000; use a conservative fixed value so
# callers do not have to think about it.
_NUM_CHUNKS: int = 8_000

# guidance_scale matches the Space's own slider default across all presets.
_GUIDANCE_SCALE: float = 5.0

# ---------------------------------------------------------------------------
# Cutout pre-processing toggles
# ---------------------------------------------------------------------------
# Set to False to disable a step without touching the helper signature, which
# is useful when debugging or comparing raw vs. cleaned inputs.
_ENABLE_ALPHA_THRESHOLD: bool = True
_ENABLE_TIGHT_CROP: bool = True

# Pixels whose alpha is strictly below this value are zeroed out.  A value of
# 10 removes faint shadow dust while leaving semi-transparent object edges
# intact.
_ALPHA_THRESHOLD: int = 10

# After cropping to the visible bounding box, a transparent square canvas is
# created whose side length equals max(crop_w, crop_h) * this ratio.  The
# extra margin prevents the diffusion model from interpreting the object as
# pressed directly against the camera lens, which causes warped, blob-like
# geometry.  1.2 adds a 20 % border on each side of the shorter axis.
_TIGHT_CROP_PADDING_RATIO: float = 1.2


def _prepare_cutout_for_hunyuan(
    pil_image: Image.Image,
    *,
    apply_alpha_threshold: bool = True,
    apply_tight_crop: bool = True,
    alpha_threshold: int = 10,
    padding_ratio: float = _TIGHT_CROP_PADDING_RATIO,
) -> Image.Image:
    """Clean an RGBA cutout before uploading it to the Hunyuan3D-2.1 Space.

    Two optional steps remove the artefacts that cause the model to generate a
    black floor or warped geometry beneath the reconstructed object:

    1. **Alpha thresholding** — pixels whose alpha value is below
       *alpha_threshold* are forced to fully transparent (A=0).  This removes
       faint shadow "pixel dust" that leaks from the segmentation mask and is
       interpreted by the model as a ground plane.

    2. **Center-and-pad crop** — after thresholding, the bounding box of all
       non-zero alpha pixels is computed via :pymeth:`PIL.Image.getbbox` and the
       image is cropped to that box.  The crop is then centered on a new
       transparent square canvas whose side length equals
       ``max(crop_w, crop_h) * padding_ratio``.  This 20 % margin prevents the
       diffusion model from treating the object as occupying the full image
       plane, which would warp perspective and produce blob-like geometry.

    Both steps are no-ops when their respective *apply_** flag is ``False``.

    Args:
        pil_image: An RGBA PIL image (the result of :func:`to_pil_rgba`).
        apply_alpha_threshold: Zero out pixels below *alpha_threshold*.
        apply_tight_crop: Crop to bounding box, then center on a padded square.
        alpha_threshold: Inclusive lower bound for "visible" alpha (0-255).
        padding_ratio: Square canvas side = max(crop dimension) * ratio.
            Defaults to :data:`_TIGHT_CROP_PADDING_RATIO` (1.2 → 20 % margin).

    Returns:
        A cleaned RGBA PIL image ready for the Hunyuan3D-2.1 Space.
    """
    img = pil_image.convert("RGBA")

    if apply_alpha_threshold:
        arr = np.array(img)
        # Zero the alpha channel for near-transparent pixels so the model does
        # not interpret shadow dust as a surface.
        arr[arr[:, :, 3] < alpha_threshold, 3] = 0
        img = Image.fromarray(arr, mode="RGBA")
        logger.debug("Alpha threshold applied: threshold=%d", alpha_threshold)

    if apply_tight_crop:
        # getbbox() operates on the alpha channel of an RGBA image and returns
        # the smallest bounding box enclosing all non-zero pixels.
        bbox = img.getbbox()
        if bbox is not None:
            cropped = img.crop(bbox)
            canvas_size = int(max(cropped.size) * padding_ratio)
            padded = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
            paste_x = (canvas_size - cropped.width) // 2
            paste_y = (canvas_size - cropped.height) // 2
            padded.paste(cropped, (paste_x, paste_y))
            logger.debug(
                "Center-pad crop applied: bbox=%s cropped_size=%s "
                "canvas_size=%d paste_offset=(%d, %d)",
                bbox,
                cropped.size,
                canvas_size,
                paste_x,
                paste_y,
            )
            img = padded
        else:
            logger.warning("getbbox() returned None (fully transparent image); skipping crop.")

    return img


class Hunyuan3D2GenerationError(RuntimeError):
    """Raised when both the textured and shape-only Hunyuan3D-2.1 calls fail."""


class Hunyuan3D2ReconstructionStrategy(Reconstruction3DStrategy):
    """Image-to-GLB strategy backed by Tencent's Hunyuan3D-2.1 Hugging Face Space.

    Calls ``tencent/Hunyuan3D-2.1`` via ``gradio_client``. On each
    :meth:`generate` call the strategy first attempts the ``/generation_all``
    endpoint (shape + texture → textured GLB). If that call fails or does not
    return a usable GLB path, it falls back to the ``/shape_generation``
    endpoint (shape only → untextured GLB). If both fail a
    :exc:`Hunyuan3D2GenerationError` is raised.

    The ``gradio_client.Client`` is created lazily on the first call to
    :meth:`generate` so that importing the module is free.

    Args:
        space_id: Hugging Face Space identifier. Defaults to
            ``"tencent/Hunyuan3D-2.1"``.
        token: Optional HF access token. When *None* the strategy reads the
            ``HF_TOKEN`` or ``HUGGINGFACE_HUB_TOKEN`` environment variables.
    """

    DEFAULT_SPACE_ID: str = "es3d-fi/hunyuan3d-2-1"

    _API_GENERATION_ALL: str = "/generation_all"
    _API_SHAPE_GENERATION: str = "/shape_generation"

    def __init__(
        self,
        space_id: str = DEFAULT_SPACE_ID,
        *,
        token: str | None = None,
    ) -> None:
        self._space_id = space_id
        self._token = token or os.environ.get("HF_TOKEN") or os.environ.get(
            "HUGGINGFACE_HUB_TOKEN"
        )
        self.__client: Any = None  # lazy; created on first generate()

    @property
    def _client(self) -> Any:
        """Return the ``gradio_client.Client``, connecting on first access."""
        if self.__client is None:
            try:
                from gradio_client import Client
            except ModuleNotFoundError as exc:
                logger.error("gradio_client not installed")
                raise RuntimeError(
                    "Missing dependency `gradio_client`. "
                    "Run: pip install 'gradio_client>=1.4'"
                ) from exc

            logger.info("Connecting to Hunyuan3D-2.1 Space: %s", self._space_id)
            self.__client = Client(self._space_id, token=self._token)
            logger.info("Connected to Space: %s", self._space_id)

        return self.__client

    def generate(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        quality: ReconstructionQuality = ReconstructionQuality.FAST,
        output: OutputMode = "bytes",
        output_path: Path | None = None,
        seed: int = 0,
    ) -> bytes | Path | BinaryIO:
        """Generate a GLB 3D model from ``image``.

        Attempts textured generation first; falls back to shape-only if the
        textured call raises or returns no GLB path.
        """
        if output not in ("bytes", "path", "file"):
            raise ValueError(
                f"output must be 'bytes', 'path', or 'file', got {output!r}."
            )

        steps, octree_resolution = _QUALITY_PARAMS[quality]

        logger.info(
            "generate called: quality=%s steps=%d octree_resolution=%d seed=%d output=%s",
            quality.value,
            steps,
            octree_resolution,
            seed,
            output,
        )

        pil_image: Image.Image = _prepare_cutout_for_hunyuan(
            to_pil_rgba(image),
            apply_alpha_threshold=_ENABLE_ALPHA_THRESHOLD,
            apply_tight_crop=_ENABLE_TIGHT_CROP,
            alpha_threshold=_ALPHA_THRESHOLD,
        )
        logger.debug("Image prepared for Hunyuan upload: size=%s", pil_image.size)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        pil_image.save(tmp_path, format="PNG")
        logger.debug("Saved input image to temp: %s", tmp_path)

        try:
            glb_path = self._generate_with_fallback(
                tmp_path, steps, octree_resolution, seed
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        glb_source = Path(glb_path)
        result = write_output(glb_source, output, output_path)

        if output == "bytes":
            assert isinstance(result, bytes)
            logger.info(
                "generate complete: quality=%s glb_bytes=%d",
                quality.value,
                len(result),
            )
        else:
            logger.info(
                "generate complete: quality=%s output=%s", quality.value, str(result)
            )

        return result

    def _generate_with_fallback(
        self,
        image_path: Path,
        steps: int,
        octree_resolution: int,
        seed: int,
    ) -> str:
        """Run textured generation; fall back to shape-only on failure.

        Returns the local filesystem path to the resulting GLB file.
        """
        try:
            from gradio_client import handle_file
        except ImportError:
            handle_file = str  # type: ignore[assignment]

        client = self._client
        image_arg = handle_file(str(image_path))
        shared_kwargs = dict(
            image=image_arg,
            steps=steps,
            guidance_scale=_GUIDANCE_SCALE,
            seed=seed,
            octree_resolution=octree_resolution,
            check_box_rembg=False,
            num_chunks=_NUM_CHUNKS,
            randomize_seed=False,
        )

        # --- Attempt 1: textured generation_all ---
        try:
            logger.debug(
                "Calling %s: steps=%d octree_resolution=%d seed=%d",
                self._API_GENERATION_ALL,
                steps,
                octree_resolution,
                seed,
            )
            result_all = client.predict(
                **shared_kwargs,
                api_name=self._API_GENERATION_ALL,
            )
            # generation_all returns (file_out, file_out2, html, stats, seed);
            # file_out2 is the textured GLB.
            glb_path = _extract_glb_path(result_all, textured=True)
            if glb_path:
                logger.debug(
                    "%s returned textured GLB path: %s",
                    self._API_GENERATION_ALL,
                    glb_path,
                )
                return glb_path
            logger.warning(
                "%s returned no GLB path; falling back to %s",
                self._API_GENERATION_ALL,
                self._API_SHAPE_GENERATION,
            )
        except Exception as exc:
            logger.warning(
                "%s call failed (%s); falling back to %s",
                self._API_GENERATION_ALL,
                exc,
                self._API_SHAPE_GENERATION,
            )

        # --- Attempt 2: shape-only shape_generation ---
        try:
            logger.debug(
                "Calling %s: steps=%d octree_resolution=%d seed=%d",
                self._API_SHAPE_GENERATION,
                steps,
                octree_resolution,
                seed,
            )
            result_shape = client.predict(
                **shared_kwargs,
                api_name=self._API_SHAPE_GENERATION,
            )
            # shape_generation returns (file_out, html, stats, seed);
            # file_out is the untextured GLB.
            glb_path = _extract_glb_path(result_shape, textured=False)
            if glb_path:
                logger.debug(
                    "%s returned shape GLB path: %s",
                    self._API_SHAPE_GENERATION,
                    glb_path,
                )
                return glb_path
        except Exception as exc:
            raise Hunyuan3D2GenerationError(
                f"Both Hunyuan3D-2.1 Space calls failed.\n"
                f"Space: {self._space_id}\n"
                f"Final error ({self._API_SHAPE_GENERATION}): {exc}\n"
                "If the Space does not expose these endpoints, call "
                "self._client.view_api() to inspect available endpoints."
            ) from exc

        raise Hunyuan3D2GenerationError(
            f"Hunyuan3D-2.1 Space returned no GLB path from either endpoint.\n"
            f"Space: {self._space_id}"
        )


def _extract_glb_path(result: Any, *, textured: bool) -> str | None:
    """Extract a local GLB filesystem path from a Gradio predict return value.

    ``generation_all`` returns a 5-tuple:
      ``(file_out, file_out2, html_gen_mesh, stats, seed)``
    where *file_out2* is the textured GLB.

    ``shape_generation`` returns a 4-tuple:
      ``(file_out, html_gen_mesh, stats, seed)``
    where *file_out* is the untextured GLB.

    Each file payload may be a plain ``str`` path, a ``dict`` (the
    ``gr.update``-style payload that Gradio produces when the component
    update carries a value), or *None*.
    """
    if not isinstance(result, (list, tuple)):
        return _path_from_payload(result)

    # generation_all → index 1 (textured); shape_generation → index 0
    idx = 1 if textured and len(result) >= 2 else 0
    return _path_from_payload(result[idx])


def _path_from_payload(payload: Any) -> str | None:
    """Normalize a single Gradio file payload to a filesystem path string."""
    if payload is None:
        return None

    if isinstance(payload, str):
        return payload or None

    if isinstance(payload, dict):
        for key in ("value", "path", "name", "url"):
            val = payload.get(key)
            if val and isinstance(val, str):
                return val

    return None
