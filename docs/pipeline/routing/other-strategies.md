# Other Routing Strategies (Experimental)

These strategies are implemented and available in `TestModules/src/routing/` but are not currently wired into `ObjectRemover`. They represent earlier iterations of the routing design.

---

## VarianceBasedRoutingStrategy

**File:** `routing/variance_based_routing_strategy.py`

### Core Idea

Computes the raw depth variance inside a dynamic local window around the click. High variance → 3D object; low variance → flat surface. This was the earliest routing approach.

### Algorithm

1. Determine depth ratio from the click point's depth value
2. Calculate a dynamic window sized between `min_ratio` and `max_ratio` of `min(H, W)`
3. Extract the depth sub-array inside that window
4. Classify: `np.var(depth_window) > variance_threshold`

### Output Context

| Condition | `input_image` | `sd_strength` | `use_broad_mask` | `expand_pixels` |
|---|---|---|---|---|
| 3D object | `adapted_depth` | `0.85` | `True` | `30 + depth_ratio×70` (up to 100px) |
| Flat surface | `rgb_image` | `0.50` | `False` | `10 + depth_ratio×30` (up to 40px) |

### Constructor Parameters

| Parameter | Default |
|---|---|
| `variance_threshold` | `20.0` |
| `min_ratio` | `0.05` |
| `max_ratio` | `0.15` |

### Limitation

The raw depth variance window can easily pick up depth variation from the floor or other nearby objects rather than the object under the cursor, leading to misclassification. The boundary ring approach in `BoundaryVarianceRoutingStrategy` was developed to address this.

---

## CenterOfMassRoutingStrategy

**File:** `routing/center_of_mass_routing_strategy.py`

### Core Idea

Gets a broad SAM probe mask, finds the object's bounding box, pads it by ~20%, then compares the median depth of object pixels to the median depth of background pixels in that padded region. High protrusion (large difference) → 3D object.

### Algorithm

1. Fetch a broad SAM probe mask at the click point
2. Find bounding box of the mask; pad by 20% (min 20px) on all sides
3. Extract depth and mask sub-arrays for that padded region
4. `protrusion = |median(object_depth) - median(background_depth)|`
5. Classify: `protrusion > protrusion_thresh`

### Output Context

Same as `VarianceBasedRoutingStrategy`: adapted depth + high SD strength for 3D, RGB + low SD strength for flat.

### Constructor Parameters

| Parameter | Default |
|---|---|
| `sam_facade` | required (injected) |
| `protrusion_thresh` | `0.03` |

### Trade-offs

Uses median rather than variance, which is more robust to noisy pixels. The local background region is well-defined (the padded bounding box). However, the broad SAM probe mask may over-expand and include floor/wall pixels in the "object" category.

---

## TopographicRoutingStrategy

**File:** `routing/topographic_routing_strategy.py`

### Core Idea

Combines two signals:
1. **Topographic range**: `max(depth_window) - min(depth_window)` — measures the depth "terrain" roughness
2. **Protrusion**: `|depth_at_click - 10th_percentile(depth_window)|` — measures how much the click point stands out above the local background baseline

An object is classified as 3D if **either** signal exceeds its threshold. This OR gate makes it more sensitive than single-signal strategies.

### Algorithm

```python
topo_range = np.max(norm_window) - np.min(norm_window)
background_baseline = np.percentile(norm_window, 10)
protrusion = abs(norm_center - background_baseline)

is_3d_object = (topo_range > self.topo_range_thresh) or (protrusion > self.protrusion_thresh)
```

The 10th percentile is used as the background baseline because most of the local window will be floor/wall (dark/far), with the object occupying a smaller fraction.

### Output Context

Same pattern as other strategies: adapted depth + high SD + broad mask for 3D, RGB + medium SD + tight mask for flat.

### Constructor Parameters

| Parameter | Default |
|---|---|
| `min_ratio` | `0.05` |
| `max_ratio` | `0.15` |
| `topo_range_thresh` | `0.08` |
| `protrusion_thresh` | `0.04` |

### Trade-offs

The OR gate increases recall for 3D objects but can over-trigger on textured walls with minor depth variation. The topographic range is sensitive to outlier depth values at the edges of the window.
