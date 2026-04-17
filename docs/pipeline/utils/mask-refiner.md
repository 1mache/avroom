# MaskRefiner

**File:** `TestModules/src/utils/MaskRefiner.py`

## Responsibility

`MaskRefiner` provides morphological mask operations used at two points in the pipeline:
1. Inside `SamFacadeSingleton` — to dilate the raw SAM mask by a router-specified number of pixels
2. Inside `ObjectRemover` — to apply a small uniform expansion with a downward bias after the tight mask is returned

## Constructor

```python
MaskRefiner(depth_tolerance: int = 10)
```

`depth_tolerance` is used only by `expand_and_clip` (see below). The other two methods do not use it.

## `dilate_mask(mask, pixels=0) → np.ndarray`

Simple symmetric dilation by `pixels` pixels in all directions using an elliptical kernel.

```python
kernel_size = pixels * 2 + 1
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
dilated = cv2.dilate(mask_uint8, kernel, iterations=1)
```

Used by `SamFacadeSingleton.get_mask_at_point` when `expand_pixels > 0`.

**Why dilation is needed:** LaMa bleeds object pixels into the background if the mask is perfectly tight. Expanding the mask by a controlled number of pixels forces LaMa to sample only from true background pixels, preventing the "halo" artifact.

## `expand_mask_uniform(original_mask, radius=3) → np.ndarray`

Applies a base 3px symmetric dilation plus a 2px extra downward expansion:

```python
# Base dilation (≈3px all around)
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius*2+1, radius*2+1))
base_dilated = cv2.dilate(mask_uint8, kernel, iterations=1)

# Downward bias
shifted = np.roll(mask_uint8, shift_pixels=2, axis=0)
shifted[:2, :] = 0  # clear wrapped rows
shifted_dilated = cv2.dilate(shifted, kernel, iterations=1)

final = np.maximum(base_dilated, shifted_dilated)
```

Used by `ObjectRemover` after the tight mask is returned from SAM. The downward bias catches the base of furniture legs and object bottoms that SAM can miss by a few pixels.

## `expand_and_clip(original_mask, depth_map, expand_pixels, click_x, click_y) → np.ndarray`

Performs dilation followed by **depth-guided clipping**: any pixel in the dilated mask whose depth is significantly farther than the click's anchor depth is removed.

```python
# 5×5 median around click as anchor depth (noise-robust)
anchor_depth = np.median(depth_map[y_min:y_max, x_min:x_max])

# Remove pixels significantly farther than the anchor
background_mask = (dilated_mask > 0) & (depth_map < (anchor_depth - depth_tolerance))
final_mask[background_mask] = 0
```

**Note:** This method is implemented and tested but is **not on the active pipeline path** in the current `ObjectRemover`. It was used in earlier iterations when `MaskRefiner` was the sole expansion mechanism. The active pipeline uses `expand_mask_uniform` instead.

## Mask Normalization

All three methods normalize the input mask to `uint8` with values 0 or 255 before processing:

```python
mask_uint8 = original_mask.astype(np.uint8)
if mask_uint8.max() == 1:
    mask_uint8 = mask_uint8 * 255
```

This handles both float masks (0.0/1.0) and binary uint8 masks (0/255).
