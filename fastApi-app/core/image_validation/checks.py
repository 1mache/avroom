from __future__ import annotations

import io
from typing import Protocol

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from settings import (
    get_upload_allowed_mime_types,
    get_upload_blur_min_variance,
    get_upload_clip_fraction_max,
    get_upload_exposure_mean_max,
    get_upload_exposure_mean_min,
    get_upload_max_aspect_ratio,
    get_upload_max_bytes,
    get_upload_max_height,
    get_upload_max_megapixels,
    get_upload_max_width,
    get_upload_min_alpha_opaque_ratio,
    get_upload_min_bytes,
    get_upload_min_spatial_variance,
    get_upload_min_height,
    get_upload_min_width,
)
from .types import ImageValidationContext, TechnicalCheckResult

# Luminance values at or beyond these bounds are treated as blown-out /
# crushed pixels when measuring how much of the frame is clipped.
_CLIP_BLACK_LEVEL = 5
_CLIP_WHITE_LEVEL = 250
_OPAQUE_ALPHA_LEVEL = 127
_MEGAPIXEL = 1_000_000.0


class TechnicalCheck(Protocol):
    """Protocol for one deterministic upload validation check."""

    name: str

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult: ...


def build_validation_context(
    file_bytes: bytes,
    *,
    filename: str | None,
    content_type: str | None,
) -> ImageValidationContext:
    """Decode bytes once and build shared validation context."""
    try:
        with Image.open(io.BytesIO(file_bytes)) as source:
            oriented = ImageOps.exif_transpose(source)
            pil_image = oriented.convert("RGBA")
    except UnidentifiedImageError as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc

    width, height = pil_image.size
    rgba = np.array(pil_image)
    rgb_array = rgba[:, :, :3]
    bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
    # Three of the checks below work on luminance; convert once here rather
    # than repeating the conversion per check.
    gray_array = cv2.cvtColor(bgr_array, cv2.COLOR_BGR2GRAY)

    alpha = rgba[:, :, 3]
    alpha_opaque_ratio = float(np.mean(alpha > _OPAQUE_ALPHA_LEVEL))

    return ImageValidationContext(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        pil_image=pil_image,
        rgb_array=rgb_array,
        bgr_array=bgr_array,
        gray_array=gray_array,
        width=width,
        height=height,
        alpha_opaque_ratio=alpha_opaque_ratio,
    )


class FileSizeCheck:
    """Reject uploads outside the configured byte-size window."""

    name = "file_size"

    def run_bytes(self, file_bytes: bytes) -> TechnicalCheckResult:
        size = len(file_bytes)
        min_bytes = get_upload_min_bytes()
        max_bytes = get_upload_max_bytes()
        if size < min_bytes:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=float(size),
                message=f"File too small ({size} bytes; minimum {min_bytes}).",
            )
        if size > max_bytes:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=float(size),
                message=f"File too large ({size} bytes; maximum {max_bytes}).",
            )
        return TechnicalCheckResult(name=self.name, passed=True, score=float(size))

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult:
        return self.run_bytes(ctx.file_bytes)


class FormatMimeCheck:
    """Reject formats outside the allow-list, sniffing magic bytes over the declared type."""

    name = "format_mime"

    @staticmethod
    def _sniff_mime(file_bytes: bytes) -> str | None:
        if len(file_bytes) >= 3 and file_bytes[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if len(file_bytes) >= 8 and file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
            return "image/webp"
        if file_bytes[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        return None

    def run_bytes(
        self,
        file_bytes: bytes,
        *,
        content_type: str | None,
    ) -> TechnicalCheckResult:
        allowed = get_upload_allowed_mime_types()
        sniffed = self._sniff_mime(file_bytes)
        if sniffed is None or sniffed not in allowed:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                message=f"Unsupported image format (detected={sniffed!r}; allowed={sorted(allowed)}).",
            )
        if content_type and content_type not in allowed:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                message=f"Content-Type {content_type!r} does not match allowed image types.",
            )
        return TechnicalCheckResult(name=self.name, passed=True, score=1.0)

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult:
        return self.run_bytes(ctx.file_bytes, content_type=ctx.content_type)


class AnimatedFrameCheck:
    """Reject multi-frame images; the pipeline only ever processes one frame."""

    name = "animated_frames"

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult:
        try:
            with Image.open(io.BytesIO(ctx.file_bytes)) as source:
                frame_count = getattr(source, "n_frames", 1)
        except UnidentifiedImageError:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                message="Could not inspect image frames.",
            )
        if frame_count > 1:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=float(frame_count),
                message=f"Animated images are not supported ({frame_count} frames).",
            )
        return TechnicalCheckResult(name=self.name, passed=True, score=float(frame_count))


class ResolutionCheck:
    """Reject images too small to segment, or too large / distorted to process."""

    name = "resolution"

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult:
        min_w = get_upload_min_width()
        min_h = get_upload_min_height()
        max_w = get_upload_max_width()
        max_h = get_upload_max_height()
        max_mp = get_upload_max_megapixels()
        max_aspect = get_upload_max_aspect_ratio()

        if ctx.width < min_w or ctx.height < min_h:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=float(ctx.width * ctx.height),
                message=f"Resolution too low ({ctx.width}x{ctx.height}; minimum {min_w}x{min_h}).",
            )
        if ctx.width > max_w or ctx.height > max_h:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=float(ctx.width * ctx.height),
                message=f"Resolution too high ({ctx.width}x{ctx.height}; maximum {max_w}x{max_h}).",
            )

        megapixels = (ctx.width * ctx.height) / _MEGAPIXEL
        if megapixels > max_mp:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=megapixels,
                message=f"Image exceeds maximum megapixels ({megapixels:.2f} > {max_mp}).",
            )

        aspect = max(ctx.width / ctx.height, ctx.height / ctx.width)
        if aspect > max_aspect:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=aspect,
                message=f"Aspect ratio too extreme ({aspect:.2f}; maximum {max_aspect}).",
            )
        return TechnicalCheckResult(name=self.name, passed=True, score=megapixels)


class AlphaEmptyCheck:
    """Reject near-fully-transparent uploads, which carry no room to edit."""

    name = "alpha_empty"

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult:
        min_ratio = get_upload_min_alpha_opaque_ratio()
        if ctx.alpha_opaque_ratio < min_ratio:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=ctx.alpha_opaque_ratio,
                message=(
                    f"Image is mostly transparent "
                    f"({ctx.alpha_opaque_ratio:.2%} opaque; minimum {min_ratio:.2%})."
                ),
            )
        return TechnicalCheckResult(name=self.name, passed=True, score=ctx.alpha_opaque_ratio)


class BlurCheck:
    """Reject out-of-focus photos via Laplacian variance."""

    name = "blur"

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult:
        variance = float(cv2.Laplacian(ctx.gray_array, cv2.CV_64F).var())
        threshold = get_upload_blur_min_variance()
        if variance < threshold:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=variance,
                message=f"Image appears too blurry (variance={variance:.2f}; minimum {threshold}).",
            )
        return TechnicalCheckResult(name=self.name, passed=True, score=variance)


class ExposureCheck:
    """Reject under/over-exposed photos and frames that are mostly clipped."""

    name = "exposure"

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult:
        gray = ctx.gray_array
        mean_luminance = float(np.mean(gray))
        clip_fraction = float(
            np.mean((gray <= _CLIP_BLACK_LEVEL) | (gray >= _CLIP_WHITE_LEVEL))
        )
        clip_max = get_upload_clip_fraction_max()
        mean_min = get_upload_exposure_mean_min()
        mean_max = get_upload_exposure_mean_max()

        if mean_luminance < mean_min:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=mean_luminance,
                message=f"Image is underexposed (mean={mean_luminance:.1f}; minimum {mean_min}).",
            )
        if mean_luminance > mean_max:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=mean_luminance,
                message=f"Image is overexposed (mean={mean_luminance:.1f}; maximum {mean_max}).",
            )
        if clip_fraction > clip_max:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=clip_fraction,
                message=f"Image has excessive clipping ({clip_fraction:.2%}; maximum {clip_max:.2%}).",
            )
        return TechnicalCheckResult(name=self.name, passed=True, score=mean_luminance)


class UniformSceneCheck:
    """Reject flat images (blank walls, solid fills) that hold no scene to edit."""

    name = "uniform_scene"

    def run(self, ctx: ImageValidationContext) -> TechnicalCheckResult:
        spatial_variance = float(np.var(ctx.gray_array))
        threshold = get_upload_min_spatial_variance()
        if spatial_variance < threshold:
            return TechnicalCheckResult(
                name=self.name,
                passed=False,
                score=spatial_variance,
                message=f"Image lacks scene detail (variance={spatial_variance:.2f}; minimum {threshold}).",
            )
        return TechnicalCheckResult(name=self.name, passed=True, score=spatial_variance)


def default_technical_checks() -> tuple[TechnicalCheck, ...]:
    """Return the ordered list of deterministic upload checks."""
    return (
        FileSizeCheck(),
        FormatMimeCheck(),
        AnimatedFrameCheck(),
        ResolutionCheck(),
        AlphaEmptyCheck(),
        BlurCheck(),
        ExposureCheck(),
        UniformSceneCheck(),
    )
