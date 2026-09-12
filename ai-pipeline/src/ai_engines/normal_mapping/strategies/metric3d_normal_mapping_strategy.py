from __future__ import annotations

import functools
import logging
import sys
import types
from typing import Any

import cv2
import numpy as np

from ..normal_mapping_strategy import NormalMappingStrategy

logger = logging.getLogger(__name__)

# Metric3D ViT input canvas from hubconf.py __main__ (keep-ratio resize + pad).
_VIT_INPUT_SIZE: tuple[int, int] = (616, 1064)
_PAD_RGB: tuple[float, float, float] = (123.675, 116.28, 103.53)
_MEAN_RGB: tuple[float, float, float] = (123.675, 116.28, 103.53)
_STD_RGB: tuple[float, float, float] = (58.395, 57.12, 57.375)


def _ensure_mmcv_stub() -> None:
    """Provide the tiny ``mmcv.utils`` surface Metric3D imports at load time.

    Full ``mmcv`` does not install cleanly on Windows + recent CPU PyTorch, and
    inference only needs ``collect_env`` (plus ``Config``, which already has an
    mmengine fallback in hubconf). If real mmcv is present, leave it alone.
    """
    try:
        import mmcv  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    from mmengine import Config, DictAction
    from mmengine.utils import get_git_hash

    mmcv_mod = types.ModuleType("mmcv")
    utils_mod = types.ModuleType("mmcv.utils")

    def collect_env() -> dict[str, str]:
        return {"avroom_mmcv_stub": "1"}

    utils_mod.collect_env = collect_env  # type: ignore[attr-defined]
    utils_mod.Config = Config  # type: ignore[attr-defined]
    utils_mod.DictAction = DictAction  # type: ignore[attr-defined]
    utils_mod.get_git_hash = get_git_hash  # type: ignore[attr-defined]
    mmcv_mod.utils = utils_mod  # type: ignore[attr-defined]

    sys.modules["mmcv"] = mmcv_mod
    sys.modules["mmcv.utils"] = utils_mod
    logger.info("Installed mmcv stub for Metric3D hub load (real mmcv not installed)")


@functools.lru_cache(maxsize=4)
def _load_metric3d(hub_model: str, device: str) -> Any:
    """Load (and cache) a Metric3D hub model on ``device``.

    Cached per ``(hub_model, device)`` so switching vit_small ↔ vit_large in
    the debug panel only pays the download/load cost once per process.
    """
    import torch

    _ensure_mmcv_stub()
    logger.info("Loading Metric3D via torch.hub: model=%s device=%s", hub_model, device)
    # trust_repo=True: Metric3D is an explicit dependency; avoids an interactive
    # prompt that would hang the FastAPI worker on first download.
    model = torch.hub.load(
        "yvanyin/metric3d",
        hub_model,
        pretrain=True,
        trust_repo=True,
    )
    model.to(device).eval()
    _patch_metric3d_for_device(model, device)
    logger.info("Metric3D loaded: model=%s device=%s", hub_model, device)
    return model


def _patch_metric3d_for_device(model: Any, device: str) -> None:
    """Rewrite Metric3D decoder helpers that hardcode ``device="cuda"``.

    Upstream ``RAFTDepthNormalDPTDecoder5.get_bins`` always allocates on CUDA,
    which crashes CPU-only PyTorch builds. Bind a replacement that uses the
    device we actually placed the model on.
    """
    import math
    import types

    import torch

    decoder = getattr(getattr(model, "depth_model", None), "decoder", None)
    if decoder is None:
        logger.warning("Metric3D decoder not found; skipping device patch")
        return

    def get_bins(self: Any, bins_num: int) -> Any:
        depth_bins_vec = torch.linspace(
            math.log(self.min_val),
            math.log(self.max_val),
            bins_num,
            device=device,
        )
        return torch.exp(depth_bins_vec)

    decoder.get_bins = types.MethodType(get_bins, decoder)  # type: ignore[method-assign]
    logger.info("Patched Metric3D decoder.get_bins for device=%s", device)


class Metric3DNormalMappingStrategy(NormalMappingStrategy):
    """Surface-normal strategy backed by Metric3D v2 (ViT hub checkpoints).

    Preprocess matches Metric3D ``hubconf.py``: keep-ratio resize into the
    ViT canvas, ImageNet pad/normalize, inference, unpad, bilinear resize
    normals back to the original HxW, then L2-normalize. Depth from the
    same forward pass is discarded — this engine only exposes normals.
    """

    DEFAULT_HUB_MODEL: str = "metric3d_vit_small"

    def __init__(
        self,
        hub_model: str = DEFAULT_HUB_MODEL,
        device: str | None = None,
    ) -> None:
        self._hub_model = hub_model
        self._device = device
        logger.info(
            "Metric3DNormalMappingStrategy created: hub_model=%s device=%s",
            hub_model,
            device or "auto",
        )

    @property
    def hub_model(self) -> str:
        return self._hub_model

    def _resolve_device(self) -> str:
        if self._device is not None:
            return self._device
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def map_normals(self, image: np.ndarray) -> np.ndarray:
        """Run Metric3D and return camera-frame unit normals at original resolution."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(
                "Normal mapping expects a BGR uint8 image with shape (H, W, 3)."
            )

        import torch

        device = self._resolve_device()
        model = _load_metric3d(self._hub_model, device)

        origin_h, origin_w = image.shape[:2]
        rgb_origin = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        input_h, input_w = _VIT_INPUT_SIZE
        scale = min(input_h / origin_h, input_w / origin_w)
        resized_w = int(origin_w * scale)
        resized_h = int(origin_h * scale)
        rgb = cv2.resize(rgb_origin, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)

        pad_h = input_h - resized_h
        pad_w = input_w - resized_w
        pad_h_half = pad_h // 2
        pad_w_half = pad_w // 2
        pad_info = (pad_h_half, pad_h - pad_h_half, pad_w_half, pad_w - pad_w_half)
        rgb = cv2.copyMakeBorder(
            rgb,
            pad_info[0],
            pad_info[1],
            pad_info[2],
            pad_info[3],
            cv2.BORDER_CONSTANT,
            value=list(_PAD_RGB),
        )

        mean = torch.tensor(_MEAN_RGB, dtype=torch.float32, device=device)[:, None, None]
        std = torch.tensor(_STD_RGB, dtype=torch.float32, device=device)[:, None, None]
        tensor = torch.from_numpy(rgb.transpose(2, 0, 1)).float().to(device)
        tensor = ((tensor - mean) / std).unsqueeze(0)

        logger.debug(
            "Metric3D normal inference: origin=%sx%s canvas=%sx%s device=%s",
            origin_h,
            origin_w,
            input_h,
            input_w,
            device,
        )

        with torch.inference_mode():
            _pred_depth, _confidence, output_dict = model.inference({"input": tensor})

        if "prediction_normal" not in output_dict:
            raise RuntimeError(
                f"Metric3D hub model '{self._hub_model}' returned no prediction_normal. "
                "Use a ViT checkpoint (metric3d_vit_small / large / giant2)."
            )

        pred_normal = output_dict["prediction_normal"][:, :3, :, :].squeeze(0)
        # CHW → unpad → HxWx3 at canvas crop, then resize to origin.
        pred_normal = pred_normal[
            :,
            pad_info[0] : pred_normal.shape[1] - pad_info[1],
            pad_info[2] : pred_normal.shape[2] - pad_info[3],
        ]
        pred_normal = torch.nn.functional.interpolate(
            pred_normal.unsqueeze(0),
            size=(origin_h, origin_w),
            mode="bilinear",
            align_corners=True,
        ).squeeze(0)
        normals = pred_normal.permute(1, 2, 0).detach().cpu().numpy().astype(np.float32)

        norms = np.linalg.norm(normals, axis=2, keepdims=True)
        normals = normals / np.maximum(norms, 1e-8)

        logger.debug(
            "Metric3D normals ready: shape=%s dtype=%s",
            normals.shape,
            normals.dtype,
        )
        return normals
