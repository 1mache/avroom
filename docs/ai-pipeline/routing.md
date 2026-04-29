# Routing Strategies

The orchestrator delegates a small "how should we treat this click?" decision to a strategy implementing [`ISegmentationRoutingStrategy`](../../TestModules/src/core/interfaces.py).

## Interface

```39:42:TestModules/src/core/interfaces.py
class ISegmentationRoutingStrategy(ABC):
    @abstractmethod
    def choose_input(self, rgb_image: np.ndarray, raw_depth: np.ndarray, adapted_depth: np.ndarray, x: int, y: int) -> dict[str, Any]:
        pass
```

The return dict drives the next two pipeline stages. Concrete strategies all return at least:

| Key | Used by |
|---|---|
| `input_image` | `SamFacadeSingleton.get_mask_at_point` (the array fed to SAM) |
| `expand_pixels` | `SamFacadeSingleton.get_mask_at_point` (dilation inside SAM) |
| `use_broad_mask` | `SamFacadeSingleton.get_mask_at_point` (currently informational) |
| `sd_strength` | `HybridInpainter.inpaint` (Stable Diffusion strength; `<=0.2` means SD is skipped) |

## The strategy in production

[`TestModules/src/routing/__init__.py`](../../TestModules/src/routing/__init__.py) only exports `BoundaryVarianceRoutingStrategy`, and the orchestrator instantiates exactly that one ([`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 47).

### `BoundaryVarianceRoutingStrategy`

[`TestModules/src/routing/boundary_variance_strategy.py`](../../TestModules/src/routing/boundary_variance_strategy.py)

The idea: probe the object with SAM, look at the **outer boundary ring** of the probe mask, and check if that ring's depth is uniform. Uniform ring = flat surface against a flat background (e.g., a TV against a wall); varied ring = a 3D object surrounded by other geometry.

```18:81:TestModules/src/routing/boundary_variance_strategy.py
    def choose_input(self, rgb_image: np.ndarray, raw_depth: np.ndarray, adapted_depth: np.ndarray, x: int, y: int) -> dict:
        h, w = raw_depth.shape[:2]
        
        pixel_depth = raw_depth[y, x, 0] if len(raw_depth.shape) == 3 else raw_depth[y, x]
        depth_ratio = float(pixel_depth) / 255.0

        # 1. Probe the object using SAM 
        # (use_broad_mask MUST be False here to avoid grabbing background objects)
        logger.info(f"Fetching probe mask at ({x}, {y}) for Boundary Analysis...")
        probe_mask = self.sam.get_mask_at_point(adapted_depth, x, y, expand_pixels=0, use_broad_mask=False)
        if probe_mask.shape[:2] != (h, w):
            probe_mask = cv2.resize(probe_mask, (w, h), interpolation=cv2.INTER_NEAREST)
        
        mask_uint8 = probe_mask.astype(np.uint8)
        
        # 2. Extract a thin ring around the object.
        # We dilate outward, then subtract the original mask, leaving only the outer band.
        # This band is the immediate neighborhood around the object.
        kernel = np.ones((7, 7), np.uint8) # 7px ring thickness
        dilated_mask = cv2.dilate(mask_uint8, kernel, iterations=1)
        boundary_ring = dilated_mask - mask_uint8
        
        # 3. Read depth values only from boundary-ring pixels.
        # If this ring has mixed depth values, the local area is likely 3D and non-flat.
        norm_depth = raw_depth.astype(float) / 255.0
        if len(norm_depth.shape) == 3:
            norm_depth = norm_depth[:, :, 0]
            
        boundary_depths = norm_depth[boundary_ring > 0]
        
        # 4. Compute depth variance on that ring.
        # High variance means uneven geometry around the object boundary.
        if len(boundary_depths) == 0:
            boundary_variance = 0.0
        else:
            boundary_variance = np.var(boundary_depths)
            
        logger.info(f"[ROUTER] Boundary Variance -> {boundary_variance:.5f} (Thresh: {self.boundary_var_thresh})")
        
        is_3d_object = boundary_variance > self.boundary_var_thresh

        # ==========================================
        # Routing Context Configuration (tuned for tighter masks)
        # ==========================================
        if is_3d_object:
            # 3D objects: slightly larger but still controlled band
            base_expand = 10
            extra_expand = int(depth_ratio * 10)  # up to +10px
        else:
            # Flat objects: very tight band
            base_expand = 4
            extra_expand = int(depth_ratio * 6)   # up to +6px

        expand_pixels = base_expand + extra_expand

        context = {
            'input_image': adapted_depth, # Use adapted depth map for robust SAM behavior.
            'sd_strength': 0.35,       # keep low to avoid SD hallucinating; sharpening is done in post
            'use_broad_mask': False,      # Request a precise object mask only (no broad background grab).
            'expand_pixels': expand_pixels
        }

        logger.info(f"[ROUTER] Decision: {'3D Object' if is_3d_object else 'Flat Surface'} | Output: {context}")
        return context
```

### Constants

| | Value | Where |
|---|---|---|
| Boundary variance threshold | `0.005` | constructor default ([`boundary_variance_strategy.py`](../../TestModules/src/routing/boundary_variance_strategy.py) line 13) |
| Ring kernel | `7×7` ones | [`boundary_variance_strategy.py`](../../TestModules/src/routing/boundary_variance_strategy.py) line 36 |
| 3D base expand / scaled extra | `10 + depth_ratio * 10` | lines 64–65 |
| Flat base expand / scaled extra | `4 + depth_ratio * 6` | lines 68–69 |
| `sd_strength` | `0.35` | line 75 |
| `input_image` | always `adapted_depth` | line 74 |
| `use_broad_mask` | always `False` | line 76 |

In other words, today the only **dynamic** output is `expand_pixels`. `sd_strength` is fixed at 0.35 (above SD's skip threshold of 0.2), and SAM is always fed the adapted depth.

## The other (currently unused) strategies

These all live in [`TestModules/src/routing/`](../../TestModules/src/routing/) but aren't exported from `__init__.py` and aren't constructed anywhere in the runtime path. They exist as alternatives that have been tried and benched.

| Strategy | File | Idea |
|---|---|---|
| `VarianceBasedRoutingStrategy` | `variance_based_routing_strategy.py` | Local depth window variance vs threshold. Picks RGB or adapted depth, broad vs tight, SD strength 0.5 vs 0.85. |
| `GradientVarianceRoutingStrategy` | `gradient_variance_routing_strategy.py` | Uses Sobel gradient variance instead of raw depth variance. |
| `TopographicRoutingStrategy` | `topographic_routing_strategy.py` | Uses depth range + protrusion percentiles in a window. |
| `CenterOfMassRoutingStrategy` | `center_of_mass_routing_strategy.py` | Probes with `use_broad_mask=True`, compares median depth inside vs around the bounding box. |

To switch the router, replace `BoundaryVarianceRoutingStrategy(sam_facade=self.sam)` in [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 47 with the desired class. None of the alternative strategies pass `use_broad_mask=True` to SAM today via the production code path.
