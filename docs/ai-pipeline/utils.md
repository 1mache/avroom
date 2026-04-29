# Utilities

Small helper modules under [`TestModules/src/utils/`](../../TestModules/src/utils/). All four are referenced by the orchestrator, the SAM facade, the inpainters, or the routing strategy.

## `MaskRefiner`

[`TestModules/src/utils/MaskRefiner.py`](../../TestModules/src/utils/MaskRefiner.py)

Three methods, two of which are wired into the live pipeline:

### `expand_mask_uniform(original_mask, radius=3)` — used

```57:81:TestModules/src/utils/MaskRefiner.py
    def expand_mask_uniform(self, original_mask: np.ndarray, radius: int = 3) -> np.ndarray:
        """
        Enlarge a binary mask by ~3 pixels in all directions,
        and ~5 pixels downward (towards increasing Y).
        Depth information and click position are NOT used here.
        """
        mask_uint8 = original_mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255

        # Base symmetric dilation (≈3px all around)
        radius = max(1, radius)
        kernel_size = radius * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        base_dilated = cv2.dilate(mask_uint8, kernel, iterations=1)

        # Extra downward bias: shift mask down by 2 pixels, then dilate and merge
        shift_pixels = 2  # extra reach downward (3 + 2 ≈ 5)
        shifted = np.roll(mask_uint8, shift_pixels, axis=0)
        # Zero out the wrapped top rows created by np.roll
        shifted[:shift_pixels, :] = 0
        shifted_dilated = cv2.dilate(shifted, kernel, iterations=1)

        final = np.maximum(base_dilated, shifted_dilated)
        return final.astype(np.uint8)
```

Used by `ObjectRemover` after SAM ([`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 138) to add a small uniform halo plus an extra ~2px downward bias (covering ground shadows of objects).

### `dilate_mask(mask, pixels=0)` — used

```83:93:TestModules/src/utils/MaskRefiner.py
    def dilate_mask(self, mask: np.ndarray, pixels: int = 0) -> np.ndarray:
        """Expand mask by `pixels` in all directions (used by SAM facade when expand_pixels > 0)."""
        if pixels <= 0:
            return mask
        mask_uint8 = mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255
        kernel_size = pixels * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        dilated = cv2.dilate(mask_uint8, kernel, iterations=1)
        return dilated.astype(np.uint8)
```

Used by `SamFacadeSingleton.get_mask_at_point` ([`SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) line 118) when the router-supplied `expand_pixels > 0`.

### `expand_and_clip(...)` — NOT currently used

```17:55:TestModules/src/utils/MaskRefiner.py
    def expand_and_clip(self, original_mask: np.ndarray, depth_map: np.ndarray, expand_pixels: int, click_x: int, click_y: int) -> np.ndarray:
```

A more aggressive depth-aware expansion that uses the click point's depth as an anchor and clips dilated pixels that lie further away than `anchor_depth - depth_tolerance`. The current `ObjectRemover` does **not** call it. The `depth_tolerance=10` passed in `ObjectRemover.__init__` only matters for this dead branch; if you re-enable depth-aware refinement, this is the method to call.

## `MaskOverlapRGBAComposer`

[`TestModules/src/utils/MaskOverlapRGBAComposer.py`](../../TestModules/src/utils/MaskOverlapRGBAComposer.py)

Static utility that builds the cutout image returned alongside the inpainted background:

```5:41:TestModules/src/utils/MaskOverlapRGBAComposer.py
class MaskOverlapRGBAComposer:
    """
    Composes a transparent view of an original image using a mask.

    Output is BGRA (OpenCV order) where:
    - alpha=255 where mask overlaps
    - alpha=0 everywhere else (pixels are fully transparent)
    """

    @staticmethod
    def compose_original_overlap_bgra(original_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if original_bgr is None or not isinstance(original_bgr, np.ndarray):
            raise ValueError("original_bgr must be a numpy ndarray")
        if mask is None or not isinstance(mask, np.ndarray):
            raise ValueError("mask must be a numpy ndarray")

        if mask.shape[:2] != original_bgr.shape[:2]:
            # SAM/depth/mask sometimes produce slightly different sizes.
            mask = cv2.resize(mask, (original_bgr.shape[1], original_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)

        if mask.dtype == bool:
            mask_bool = mask
        else:
            mask_max = float(np.max(mask)) if mask.size else 0.0
            if mask_max <= 1.0:
                mask_bool = mask > 0.5
            else:
                mask_bool = mask > 127

        alpha = mask_bool.astype(np.uint8) * 255

        # Convert to BGRA then apply alpha and (optionally) zero out transparent RGB.
        bgra = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2BGRA)
        bgra[..., 3] = alpha
        bgra[..., :3] = bgra[..., :3] * mask_bool.astype(np.uint8)[..., None]
        return bgra
```

Note that the BGR channels outside the mask are zeroed (line 39). The frontend renders this BGRA via `cv2.imencode(".png", ...)` → base64 → `<img src="data:image/png;base64,...">`.

## `DebugImageSaver`

[`TestModules/src/utils/DebugImageSaver.py`](../../TestModules/src/utils/DebugImageSaver.py)

```13:51:TestModules/src/utils/DebugImageSaver.py
    def __init__(self, output_folder_name: str = "outputs"):
        # Calculate project root dynamically (assuming file is in src/utils/)
        # This goes up two levels: utils -> src -> TestModules
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
        self.output_dir = os.path.join(self.project_root, output_folder_name)
        
        # Ensure the outputs directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"DebugImageSaver initialized. Saving to: {self.output_dir}")

    def save(self, filename: str, image: np.ndarray) -> str:
        """
        Saves a numpy array (OpenCV image) to the configured outputs directory.
        Automatically handles boolean masks and appends .png if needed.
        """
        if image is None or not isinstance(image, np.ndarray):
            logger.warning(f"Cannot save {filename}: invalid image data.")
            return ""

        # Critical SAM-mask fix:
        # If the image is boolean (True/False), convert it to uint8 black/white (0/255)
        # so OpenCV writes a visible image instead of a nearly empty file.
        save_image = image
        if save_image.dtype == bool:
            save_image = (save_image * 255).astype(np.uint8)

        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            filename += '.png'
            
        filepath = os.path.join(self.output_dir, filename)
        ...
```

Key facts:

- The output directory is **always** `TestModules/outputs/` regardless of where the package is installed from. Path is computed relative to the file (`utils/ -> src/ -> TestModules/`).
- Boolean masks are auto-converted to `uint8 * 255` so they're visible PNGs instead of all-black.
- `.png` is appended automatically if the caller passes a bare name.

This util is created in many places ([`ObjectRemover`](../../TestModules/src/core/objectRemover.py) line 50, [`SamFacadeSingleton.get_mask_at_point`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) line 109, [`HybridInpainter`](../../TestModules/src/ai_engines/inpainting/HybridInpainter.py) line 23). They all write to the same folder.

## `ImageAdapterFactory`

[`TestModules/src/utils/imageAdapterFactory.py`](../../TestModules/src/utils/imageAdapterFactory.py)

A singleton that loads either a file path or a PIL image into an RGB numpy array:

```22:57:TestModules/src/utils/imageAdapterFactory.py
    def create_image(self, source: str | Path | PILImage) -> np.ndarray:
        """
        Load and convert image from a file path or PIL Image to a numpy array
        acceptable by LamaInpainterFacade and SamFacade.
        ...
        """
        logger.debug(f"Creating image from source: {source}")
        # If a PIL image was supplied directly, skip file handling
        if isinstance(source, PILImage):
            logger.debug("Source is already a PIL Image")
            image = source
        else:
            image_path = Path(source)
            logger.debug(f"Loading image from path: {image_path}")
            if not image_path.exists():
                logger.error(f"Image not found: {image_path}")
                raise FileNotFoundError(f"Image not found: {image_path}")
            image = Image.open(image_path)
            logger.debug(f"Image loaded: {image.size} {image.mode}")
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            logger.debug(f"Converting image from {image.mode} to RGB")
            image = image.convert('RGB')
        
        # Convert to numpy array
        image_array = np.array(image)
        logger.debug(f"Image converted to numpy array: {image_array.shape}")
        
        return image_array
```

Currently it is used **only by the test scripts** (e.g., [`samMasksTest.py`](../../TestModules/tests/samMasksTest.py) line 8). The HTTP path uses `cv2.imread` / `cv2.imdecode` directly inside `ObjectRemover.remove_object`. The factory and its `get_image_adapter_factory()` accessor stay around for the test/GUI paths and as a future entry point.
