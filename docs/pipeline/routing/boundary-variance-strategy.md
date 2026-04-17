# BoundaryVarianceRoutingStrategy

**File:** `TestModules/src/routing/boundary_variance_strategy.py`

**Status: ACTIVE** — this is the strategy wired into `ObjectRemover`.

## Core Idea

Instead of analyzing the depth window around the click, this strategy asks: "how varied is the depth of the immediate neighborhood *around* the object's outline?" A 3D object (sofa, chair) will have highly varied depth just outside its boundary because it protrudes from the floor. A flat object (TV, picture) will have uniform depth just outside its boundary because it lies flush with the wall.

## Algorithm

### Step 1 — Probe Mask

SAM is called with zero expansion to get a tight probe mask at the click point:

```python
probe_mask = self.sam.get_mask_at_point(
    adapted_depth, x, y, expand_pixels=0, use_broad_mask=False
)
```

`use_broad_mask=False` is required here to avoid accidentally pulling in background objects adjacent to the clicked object.

### Step 2 — Boundary Ring Extraction

A 7px dilation is applied to the probe mask, then the original mask is subtracted:

```python
kernel = np.ones((7, 7), np.uint8)
dilated_mask = cv2.dilate(mask_uint8, kernel, iterations=1)
boundary_ring = dilated_mask - mask_uint8
```

`boundary_ring` is a thin band of pixels immediately outside the object.

### Step 3 — Depth Variance on the Ring

The normalized depth values of all ring pixels are collected and their variance computed:

```python
boundary_depths = norm_depth[boundary_ring > 0]
boundary_variance = np.var(boundary_depths)
```

### Step 4 — Classification

```python
is_3d_object = boundary_variance > self.boundary_var_thresh  # default: 0.005
```

### Step 5 — Expand Pixels Calculation

Expansion is further modulated by the click point's depth ratio (brighter = closer = larger object footprint):

```python
pixel_depth = raw_depth[y, x]
depth_ratio = float(pixel_depth) / 255.0  # 0.0 = far, 1.0 = near

if is_3d_object:
    base_expand = 10
    extra_expand = int(depth_ratio * 10)  # up to +10px
else:
    base_expand = 4
    extra_expand = int(depth_ratio * 6)   # up to +6px

expand_pixels = base_expand + extra_expand  # range: 4–14 (flat) or 10–20 (3D)
```

## Output Context

```python
{
    'input_image': adapted_depth,  # always uses depth map as SAM input
    'sd_strength': 0.35,           # conservative; sharpening done in post
    'use_broad_mask': False,       # precise object mask only
    'expand_pixels': expand_pixels # 4–20px depending on type and distance
}
```

Note: `input_image` is always `adapted_depth` regardless of 3D/flat classification. This is a deliberate design choice — the depth-based SAM input is more reliable for both object types in the current tuning.

## Constructor Parameters

| Parameter | Default | Description |
|---|---|---|
| `sam_facade` | required | Injected `SamFacadeSingleton` instance for probe mask generation |
| `boundary_var_thresh` | `0.005` | Variance threshold for 3D vs flat classification |

## Why This Outperforms Window-Based Strategies

Window-based strategies (e.g., `VarianceBasedRoutingStrategy`) analyze a square region around the click. This region may include the object itself, noisy pixels, or unrelated nearby geometry. The boundary ring analysis isolates exactly the pixels that define what is *behind* the object boundary, giving a much cleaner signal for the 3D/flat decision.
