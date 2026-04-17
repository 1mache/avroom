# SamFacadeSingleton

**File:** `TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py`

## Responsibility

`SamFacadeSingleton` is a Singleton Facade that:
1. Loads the SAM ViT-B model into memory exactly once per process.
2. Exposes a simple `get_mask_at_point(image, x, y)` interface that hides all SAM API complexity.
3. Applies post-prediction dilation via a composed `MaskRefiner`.

## Why a Singleton?

SAM ViT-B weighs ~375 MB. Loading it multiple times would exhaust GPU/CPU memory and slow startup. The singleton ensures that both `ObjectRemover` and any routing strategy that needs a probe mask share the same loaded model instance.

## Checkpoint Resolution

The checkpoint is resolved in the following priority order:

1. `SAM_CHECKPOINT_PATH` environment variable (must point to an existing `.pth` file)
2. Default path: `TestModules/checkpoints/sam_vit_b_01ec64.pth`
3. Auto-download from `https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth` (unless `SAM_AUTO_DOWNLOAD=0`)

The download URL can be overridden via `SAM_CHECKPOINT_URL`.

## Device Selection

CUDA is used automatically if `torch.cuda.is_available()` is `True`; otherwise CPU is used.

## `get_mask_at_point(image, x, y, expand_pixels=30, use_broad_mask=False)`

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `image` | `np.ndarray` | — | The image to segment (typically the adapted depth map, not RGB) |
| `x`, `y` | `int` | — | Click coordinates in pixels |
| `expand_pixels` | `int` | `30` | Dilation applied to the chosen mask via `MaskRefiner.dilate_mask` |
| `use_broad_mask` | `bool` | `False` | Currently unused in the mask selection logic (reserved for future use) |

### Returns

Binary mask as `uint8 np.ndarray` of shape `(H, W)`.

### Internals

1. `self._predictor.set_image(image)` — encodes the image into SAM's embedding space
2. Formats the click as `input_point = [[x, y]]`, `input_label = [1]` (foreground)
3. `self._predictor.predict(multimask_output=True)` — returns 3 mask candidates
4. **`masks[1]` is always selected** — this is SAM's "tight" mask, which avoids over-segmenting nearby objects. `masks[0]` is the smallest and `masks[2]` is the largest.
5. If `expand_pixels > 0`: calls `self.mask_refiner.dilate_mask(best_mask, pixels=expand_pixels)`
6. All three raw masks and the final dilated mask are saved via `DebugImageSaver`

## Why SAM Receives the Depth Map, Not RGB

SAM is highly sensitive to texture: fabric creases, shadows, and surface patterns can cause it to segment only part of a sofa or grab neighboring objects. The smooth, texture-free depth map provides SAM with pure geometric boundaries, leading to much more accurate whole-object masks.

## Composition: MaskRefiner

`SamFacadeSingleton` composes (owns) a `MaskRefiner` instance:
```python
self.mask_refiner = MaskRefiner()
```

This is used exclusively for `dilate_mask` inside `get_mask_at_point`. The `MaskRefiner` in `ObjectRemover` is a separate instance used for `expand_mask_uniform` after the tight mask is returned.
