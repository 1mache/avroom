# OptimizedDepthFacade

**File:** `TestModules/src/ai_engines/depth/OptimizedDepthFacade.py`

## Responsibility

`OptimizedDepthFacade` solves the **near-far depth problem**: no single depth model reliably handles both foreground objects and background walls in the same scene. This facade runs two models and soft-blends them into a single high-quality depth map.

It implements `IDepthFacade`.

## The Near-Far Problem

| Model | Strength | Weakness |
|---|---|---|
| `Depth-Anything-V2-Small-hf` | Accurate for near-field / foreground objects | Degrades on far walls, ceilings |
| `LiheYoung/depth-anything-small-hf` | Accurate for far-field / background surfaces | Less precise on close objects |

Using either model alone causes artifacts: walls appear at incorrect depths, or object boundaries are smeared. Blending both models eliminates hard seams.

## Alpha Compositing Blend

The blend uses the V2 model's own normalized depth values as the alpha weight:

```
alpha         = depth_v2_normalized / 255
optimized     = (depth_v2_norm × alpha) + (depth_lihe_norm × (1 - alpha))
```

This means:
- Where V2 is confident (bright/near pixels), V2 dominates.
- Where V2 is weak (dark/far pixels), LiheYoung takes over.
- The transition is smooth — no sharp seam between near and far.

## Implementation Steps

```python
# 1. Generate Near-Field Map (V2)
self.depth_mapper.model = "depth-anything/Depth-Anything-V2-Small-hf"
depth_v2 = np.array(self.depth_mapper.get_depth_map(image))
depth_v2 = cv2.cvtColor(depth_v2, cv2.COLOR_RGB2GRAY)  # if 3-channel

# 2. Generate Far-Field Map (LiheYoung)
self.depth_mapper.model = "LiheYoung/depth-anything-small-hf"
depth_lihe = np.array(self.depth_mapper.get_depth_map(image))
depth_lihe = cv2.cvtColor(depth_lihe, cv2.COLOR_RGB2GRAY)

# 3. Normalize both to 0–255 float
depth_v2_norm   = cv2.normalize(depth_v2,   None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)
depth_lihe_norm = cv2.normalize(depth_lihe, None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)

# 4. Alpha compositing
alpha = depth_v2_norm / 255.0
optimized_depth = (depth_v2_norm * alpha) + (depth_lihe_norm * (1.0 - alpha))

return optimized_depth.astype(np.uint8)
```

## Output

A single `uint8` grayscale numpy array of the same spatial dimensions as the input image. Brighter values = closer to the camera (higher depth).

## Why This Matters for SAM

The blended depth map is passed to `SamImageAdapter`, which converts it to RGB for SAM's input. SAM receives smooth geometric contours free from wall/object boundary artifacts. See [`sam-image-adapter.md`](../segmentation/sam-image-adapter.md).

## Constructor Parameter

| Parameter | Default | Description |
|---|---|---|
| `threshold` | `100` | Reserved parameter; not used in the current blending logic |
