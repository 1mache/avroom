from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
from PIL import Image

from ..reconstruction_3d_strategy import OutputMode, Reconstruction3DStrategy
from ..reconstruction_glb_writer import write_output
from ..reconstruction_image_input import to_pil_rgba
from ..reconstruction_quality import PRESETS, GenerationParams, ReconstructionQuality

logger = logging.getLogger(__name__)


class Trellis3DGenerationError(RuntimeError):
    """Raised when the Trellis 2 Space call fails."""


class TrellisReconstructionStrategy(Reconstruction3DStrategy):
    """Image-to-GLB strategy backed by Microsoft's Trellis 2 Hugging Face Space.

    The strategy calls the public Space ``microsoft/TRELLIS.2`` using
    ``gradio_client``. The Space runs on Zero GPU and is rate-limited /
    queued; it is fine for MVP single-user testing but unsuitable for
    high-concurrency production.

    The ``gradio_client.Client`` is lazily connected on the first
    :meth:`generate` call to avoid paying the handshake cost at import time.
    """

    DEFAULT_SPACE_ID: str = "microsoft/TRELLIS.2"

    # API names as registered in the Space's Gradio app.
    _API_IMAGE_TO_3D: str = "/image_to_3d"
    _API_EXTRACT_GLB: str = "/extract_glb"

    def __init__(
        self,
        space_id: str = DEFAULT_SPACE_ID,
        *,
        hf_token: str | None = None,
    ) -> None:
        self._space_id = space_id
        self._hf_token = hf_token
        self.__client: Any = None  # lazy on first generate()

    @property
    def _client(self) -> Any:
        if self.__client is None:
            try:
                from gradio_client import Client
            except ModuleNotFoundError as exc:
                logger.error("gradio_client not installed")
                raise RuntimeError(
                    "Missing dependency `gradio_client`. "
                    "Run: pip install 'gradio_client>=1.4'"
                ) from exc

            logger.info("Connecting to Trellis 2 Space: %s", self._space_id)
            self.__client = Client(self._space_id, hf_token=self._hf_token)
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
        if output not in ("bytes", "path", "file"):
            raise ValueError(f"output must be 'bytes', 'path', or 'file', got {output!r}.")

        params: GenerationParams = PRESETS[quality]

        logger.info(
            "generate called: quality=%s resolution=%s seed=%d output=%s",
            quality.value,
            params.resolution,
            seed,
            output,
        )

        pil_image: Image.Image = to_pil_rgba(image)
        logger.debug("Image converted to RGBA: size=%s", pil_image.size)

        # gradio_client uploads the image from disk; write a tempfile.
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        pil_image.save(tmp_path, format="PNG")
        logger.debug("Saved input image to temp: %s", tmp_path)

        try:
            _state_dict, glb_path = self._call_space(tmp_path, params, seed)
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
            logger.info("generate complete: quality=%s output=%s", quality.value, str(result))

        return result

    def _call_space(
        self,
        image_path: Path,
        params: GenerationParams,
        seed: int,
    ) -> tuple[object, str]:
        """Run the two-step Trellis 2 Space API and return (state_dict, glb_path)."""

        try:
            from gradio_client import handle_file
        except ImportError:
            handle_file = str  # type: ignore[assignment]  # older client fallback

        client = self._client

        logger.debug(
            "Calling %s: resolution=%s steps=%d/%d/%d seed=%d",
            self._API_IMAGE_TO_3D,
            params.resolution,
            params.ss_sampling_steps,
            params.shape_slat_sampling_steps,
            params.tex_slat_sampling_steps,
            seed,
        )
        try:
            step1_result = client.predict(
                handle_file(str(image_path)),
                seed,
                params.resolution,
                params.ss_guidance_strength,
                params.ss_guidance_rescale,
                params.ss_sampling_steps,
                params.ss_rescale_t,
                params.shape_slat_guidance_strength,
                params.shape_slat_guidance_rescale,
                params.shape_slat_sampling_steps,
                params.shape_slat_rescale_t,
                params.tex_slat_guidance_strength,
                params.tex_slat_guidance_rescale,
                params.tex_slat_sampling_steps,
                params.tex_slat_rescale_t,
                api_name=self._API_IMAGE_TO_3D,
            )
        except Exception as exc:
            logger.error("image_to_3d call failed: %s", exc)
            raise Trellis3DGenerationError(
                f"Trellis 2 Space call failed at image_to_3d: {exc}\n"
                f"Space: {self._space_id}\n"
                "If the Space does not expose this API endpoint, call "
                "self._client.view_api() to inspect available endpoints."
            ) from exc

        if isinstance(step1_result, (list, tuple)):
            state_dict = step1_result[0]
        else:
            state_dict = step1_result
        logger.debug("image_to_3d returned state (type=%s)", type(state_dict).__name__)

        logger.debug(
            "Calling %s: decimation=%d texture_size=%d",
            self._API_EXTRACT_GLB,
            params.decimation_target,
            params.texture_size,
        )
        try:
            step2_result = client.predict(
                state_dict,
                params.decimation_target,
                params.texture_size,
                api_name=self._API_EXTRACT_GLB,
            )
        except Exception as exc:
            logger.error("extract_glb call failed: %s", exc)
            raise Trellis3DGenerationError(
                f"Trellis 2 Space call failed at extract_glb: {exc}\n"
                f"Space: {self._space_id}"
            ) from exc

        if isinstance(step2_result, (list, tuple)):
            glb_path = step2_result[0]
        else:
            glb_path = step2_result

        if isinstance(glb_path, dict):
            glb_path = glb_path.get("path") or glb_path.get("name") or glb_path.get("url")

        logger.debug("extract_glb returned path: %s", glb_path)
        return state_dict, str(glb_path)
