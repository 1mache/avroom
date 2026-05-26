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

    DEFAULT_SPACE_ID: str = "tencent/Hunyuan3D-2.1"

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

        pil_image: Image.Image = to_pil_rgba(image)
        logger.debug("Image converted to RGBA: size=%s", pil_image.size)

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
            check_box_rembg=True,
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
