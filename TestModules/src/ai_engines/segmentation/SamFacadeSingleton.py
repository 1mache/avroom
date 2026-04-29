import os
import torch
import logging
import numpy as np
import urllib.request
from pathlib import Path
from segment_anything import sam_model_registry, SamPredictor
from ...utils.DebugImageSaver import DebugImageSaver

# Import mask post-processing helper used by SAM output flow.
from ...utils.MaskRefiner import MaskRefiner

logger = logging.getLogger(__name__)


SAM_CHECKPOINT_NAME = "sam_vit_b_01ec64.pth"
SAM_DEFAULT_URL = f"https://dl.fbaipublicfiles.com/segment_anything/{SAM_CHECKPOINT_NAME}"


def _get_default_checkpoint_path() -> Path:
    current_dir = Path(__file__).resolve().parent
    return (current_dir / ".." / ".." / ".." / "checkpoints" / SAM_CHECKPOINT_NAME).resolve()


def _resolve_checkpoint_path() -> Path:
    # Resolution order:
    # 1) explicit env var path
    # 2) local default checkpoint file
    # 3) optional auto-download fallback
    env_path = os.getenv("SAM_CHECKPOINT_PATH")
    if env_path:
        explicit = Path(env_path).expanduser().resolve()
        if explicit.exists():
            return explicit
        raise FileNotFoundError(
            f"SAM_CHECKPOINT_PATH points to missing file: {explicit}"
        )

    checkpoint_path = _get_default_checkpoint_path()
    if checkpoint_path.exists():
        return checkpoint_path

    auto_download = os.getenv("SAM_AUTO_DOWNLOAD", "1").strip().lower() not in {"0", "false", "no"}
    if not auto_download:
        raise FileNotFoundError(
            f"Missing SAM checkpoint: {checkpoint_path}. "
            f"Set SAM_CHECKPOINT_PATH or enable SAM_AUTO_DOWNLOAD=1."
        )

    checkpoint_url = os.getenv("SAM_CHECKPOINT_URL", SAM_DEFAULT_URL)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Downloading SAM checkpoint from {checkpoint_url} -> {checkpoint_path}")
    urllib.request.urlretrieve(checkpoint_url, checkpoint_path)
    logger.info("SAM checkpoint download complete")
    return checkpoint_path

class SamFacadeSingleton:
    """
    Singleton Facade for the Segment Anything Model (SAM).
    Composed with a MaskRefiner to handle post-processing.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SamFacadeSingleton, cls).__new__(cls)
            cls._instance._is_initialized = False
        return cls._instance

    def __init__(self):
        if not self._is_initialized:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"SamFacadeSingleton initializing on {device}")

            checkpoint_path = _resolve_checkpoint_path()
            model_type = "vit_b"
            
            try:
                # 1. Loading the AI Engine
                sam = sam_model_registry[model_type](checkpoint=str(checkpoint_path))
                sam.to(device=device)
                self._predictor = SamPredictor(sam)
                
                # 2. Composition: Injecting the MaskRefiner component
                self.mask_refiner = MaskRefiner()
                
                logger.info("SAM model loaded successfully")
                self._is_initialized = True
            except Exception as e:
                logger.error(f"Error loading SAM model: {e}")
                raise

    # ADDED 'use_broad_mask' parameter defaulting to False
    def get_mask_at_point(self, image: np.ndarray, x: int, y: int, expand_pixels: int = 30, use_broad_mask: bool = False) -> np.ndarray:
        # 1. Feed the image to SAM
        self._predictor.set_image(image)
        
        # 2. Format the coordinates for SAM (This is what got deleted!)
        input_point = np.array([[x, y]])
        input_label = np.array([1]) # 1 indicates a foreground point
        
        # 3. Predict masks
        masks, scores, logits = self._predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=True,
        )
        
        image_saver = DebugImageSaver()
        for i, mask in enumerate(masks):
            image_saver.save(f"mask_{i}.png", mask)

        best_mask = masks[1]  # The tight mask (good for flat TVs and Windows)

        # 5. Dynamic Expansion
        if expand_pixels > 0:
          
            best_mask = self.mask_refiner.dilate_mask(best_mask, pixels=expand_pixels)
            image_saver.save("dilated_mask.png", best_mask)
        image_saver.save("best_mask.png", best_mask)
        return best_mask

        
