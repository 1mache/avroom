# MaskOverlapRGBAComposer

**File:** `TestModules/src/utils/MaskOverlapRGBAComposer.py`

## Responsibility

`MaskOverlapRGBAComposer` creates the "cutout" output: a transparent image that shows the original pixels only where the segmentation mask was active. All pixels outside the mask are fully transparent (alpha = 0).

This is a pure static utility class — no instance state, no model loading.

## `compose_original_overlap_bgra(original_bgr, mask) → np.ndarray`

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `original_bgr` | `np.ndarray` | Source image in BGR format (OpenCV) |
| `mask` | `np.ndarray` | Binary or boolean mask; non-zero / `True` = object pixels |

### Returns

A `(H, W, 4)` `uint8` numpy array in **BGRA** order where:
- Channels 0–2 (B, G, R): original pixel color, zeroed out outside the mask
- Channel 3 (A): 255 inside the mask, 0 outside

### Algorithm

```python
# Normalize mask to boolean
mask_bool = mask > 127  # or > 0.5 for float masks

# Create alpha channel
alpha = mask_bool.astype(np.uint8) * 255

# Add alpha channel to image
bgra = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2BGRA)
bgra[..., 3] = alpha

# Zero out RGB for transparent pixels
bgra[..., :3] = bgra[..., :3] * mask_bool.astype(np.uint8)[..., None]
```

### Size Mismatch Handling

If `original_bgr` and `mask` have different spatial dimensions, the mask is resized to match the image using `cv2.INTER_NEAREST` (preserves hard edges of binary masks).

### Validation

Both inputs are validated as non-None numpy arrays before processing. A `ValueError` is raised if either is missing or wrong type.

## Usage in the Pipeline

`ObjectRemover` calls this as the final step after inpainting:

```python
original_bg_ra = MaskOverlapRGBAComposer.compose_original_overlap_bgra(
    original_bgr=image,
    mask=mask,
)
```

The result (`cutout_bgra`) is one of the two outputs returned to the API, which encodes it as a base64 PNG. The frontend renders it as a transparent PNG to show the user what was removed.
