# GradientVarianceRoutingStrategy

**File:** `TestModules/src/routing/gradient_variance_routing_strategy.py`

**Status: Inactive** — available as a drop-in alternative to `BoundaryVarianceRoutingStrategy`.

## Core Idea

Flat surfaces (walls, screens) have a nearly constant depth gradient — the Sobel filter produces similar values everywhere. Curved or structured 3D objects (sofas, chairs, boxes) have continuously changing surface normals, which produces a high-variance Sobel gradient field. This strategy uses that signal to classify the object type.

## Algorithm

### Step 1 — Dynamic Window Sizing

A square window around the click is sized proportionally to the image and the click's depth:

```python
base_image_size = min(h, w)
min_window = int(base_image_size * self.min_ratio)   # default: 5% of min dim
max_window = int(base_image_size * self.max_ratio)   # default: 15% of min dim
dynamic_window_size = int(min_window + depth_ratio * (max_window - min_window))
```

A near click (depth_ratio ≈ 1.0) gets a larger window; a far click (depth_ratio ≈ 0.0) gets a smaller one.

### Step 2 — Sobel Gradient Variance

```python
grad_x = cv2.Sobel(norm_window, cv2.CV_64F, 1, 0, ksize=3)
grad_y = cv2.Sobel(norm_window, cv2.CV_64F, 0, 1, ksize=3)
magnitude = cv2.magnitude(grad_x, grad_y)
grad_variance = np.var(magnitude)
```

### Step 3 — Classification

```python
is_3d_object = grad_variance > self.gradient_var_thresh  # default: 0.002
```

## Output Context

| Condition | `input_image` | `sd_strength` | `use_broad_mask` | `expand_pixels` |
|---|---|---|---|---|
| 3D object | `adapted_depth` | `0.85` | `True` | `30 + depth_ratio×60` (30–90px) |
| Flat surface | `rgb_image` | `0.50` | `False` | `10 + depth_ratio×20` (10–30px) |

Unlike `BoundaryVarianceRoutingStrategy`, this strategy switches the SAM input between depth and RGB depending on the classification, and uses higher SD strength values for 3D objects.

## Constructor Parameters

| Parameter | Default | Description |
|---|---|---|
| `min_ratio` | `0.05` | Minimum local window as a fraction of min(H,W) |
| `max_ratio` | `0.15` | Maximum local window as a fraction of min(H,W) |
| `gradient_var_thresh` | `0.002` | Variance threshold for 3D vs flat classification |

## Trade-offs vs BoundaryVarianceStrategy

- Does not require a SAM probe mask call, so it is faster
- The window may overlap nearby objects or be too small/large for unusual image sizes
- Does not inject SAM as a dependency, making it simpler to instantiate
