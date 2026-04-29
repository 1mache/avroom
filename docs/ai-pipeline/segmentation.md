# Segmentation (SAM)

Two files: the singleton facade that owns the SAM model, and the adapter that converts depth maps into a SAM-compatible RGB array.

## `SamFacadeSingleton`

[`TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py)

### Checkpoint resolution

```20:55:TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py
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
```

Order:

1. `SAM_CHECKPOINT_PATH` env var (must exist if set).
2. `TestModules/checkpoints/sam_vit_b_01ec64.pth` (the default location).
3. Auto-download from `https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth` (overridable with `SAM_CHECKPOINT_URL`), unless `SAM_AUTO_DOWNLOAD` is set to `0`/`false`/`no`.

### Loading

```70:91:TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py
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
```

`vit_b` (the smallest SAM variant) is hardcoded.

### `get_mask_at_point`

```93:121:TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py
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
```

Things to know:

- `multimask_output=True` produces three candidate masks; SAM convention is roughly `[whole, tight, parts]`. The pipeline always picks index `1` — the tight one. This is the implicit assumption behind everything downstream.
- `use_broad_mask` is accepted in the signature but **not actually branched on** in the body. Today the parameter is informational only; the router still threads it through, but the facade behaves the same regardless.
- Each call writes `mask_0.png`, `mask_1.png`, `mask_2.png`, optionally `dilated_mask.png`, and always `best_mask.png` to `TestModules/outputs/`.
- `expand_pixels` is the **router-controlled** dilation radius applied right inside SAM (not a generic later step).

### Two callers, same method

`get_mask_at_point` is called twice per pipeline run:

1. By [`BoundaryVarianceRoutingStrategy`](../../TestModules/src/routing/boundary_variance_strategy.py) (line 27) for a probe mask with `expand_pixels=0`.
2. By [`ObjectRemover`](../../TestModules/src/core/objectRemover.py) (lines 116–121) for the actual tight mask with the router-decided `expand_pixels`.

The probe and the real call therefore overwrite each other's `mask_*.png` and `best_mask.png` debug PNGs in `outputs/` — the saved files reflect the **second** call.

## `SamImageAdapter` and `CacheComponent`

[`TestModules/src/ai_engines/segmentation/SamImageAdapter.py`](../../TestModules/src/ai_engines/segmentation/SamImageAdapter.py)

```28:67:TestModules/src/ai_engines/segmentation/SamImageAdapter.py
class SamImageAdapter(IImageAdapter):
    """
    Adapter to convert raw depth maps into SAM-compatible RGB numpy arrays.
    Uses Composition to implement caching.
    """
    def __init__(self):
        # Composition: the adapter owns a dedicated cache component.
        self._cache = CacheComponent()
        logger.info("SamImageAdapter initialized")

    def get_adapted_image(self, raw_data: Any, image_id: str, point: tuple[int, int]) -> np.ndarray:
        # Create a unique key based on both the image identity and the clicked point
        cache_key = f"{image_id}_{point[0]}_{point[1]}"
        
        # Check cache first
        cached_image = self._cache.get(cache_key)
        if cached_image is not None:
            logger.info("Using cached adapted image")
            print("[Adapter] Using CACHED adapted image.")
            return cached_image

        logger.info("Adapting new data for SAM and caching it...")
        print("[Adapter] Adapting new data for SAM and caching it...")
        
        # Adaptation Logic: Convert to Numpy
        adapted = np.array(raw_data)
        
        # SAM requires 3 channels (RGB). If depth map is 1 channel (Grayscale), convert it.
        if len(adapted.shape) == 2:
            logger.debug("Converting grayscale depth to RGB")
            adapted = cv2.cvtColor(adapted, cv2.COLOR_GRAY2RGB)
        elif len(adapted.shape) == 3 and adapted.shape[2] == 4:
            logger.debug("Converting RGBA to RGB")
            adapted = cv2.cvtColor(adapted, cv2.COLOR_RGBA2RGB)
            
        # Save to cache using the composed component
        self._cache.set(cache_key, adapted)
        logger.debug(f"Adapted image cached with key: {cache_key}")
        
        return adapted
```

- The cache is **single-entry** (`CacheComponent` only stores one `(key, data)` pair, lines 11–25). Re-clicking the same point on the same image hits cache; any other key replaces it.
- The cache key is `"{image_id}_{x}_{y}"`. The HTTP path uses `image_id = "memory://<sha256>"`, so identical bytes hit the same cache slot.

## Why depth → SAM

The `objectRemover.py` flow feeds the **depth-derived RGB** (not the original RGB) to SAM. This is one of the AI lessons baked into the project (also noted in [../conventions.md](../conventions.md)):

- SAM is sensitive to texture, fabric creases, shadows; with RGB it tends to segment "the cushion of a sofa" instead of "the whole sofa".
- A smooth depth map gives clean geometric boundaries, so SAM produces a single mask covering the whole object.
- The cost is that depth has to be good enough first — hence the two-model alpha blend in [depth.md](depth.md).
