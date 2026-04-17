# Interfaces

**File:** `TestModules/src/core/interfaces.py`

All pipeline components are defined against abstract base classes. This allows implementations to be swapped without modifying `ObjectRemover` or any caller.

## `IDepthFacade`

```python
class IDepthFacade(ABC):
    @abstractmethod
    def get_optimized_depth_map(self, image: np.ndarray) -> np.ndarray:
        pass
```

**Purpose:** Generate a single, optimized depth map from an input image.

**Implemented by:** `OptimizedDepthFacade`

**Contract:**
- Input: BGR `np.ndarray` (OpenCV format)
- Output: single-channel or uint8 `np.ndarray` representing depth (brighter = closer)

---

## `IImageAdapter`

```python
class IImageAdapter(ABC):
    @abstractmethod
    def get_adapted_image(self, raw_data: Any, image_id: str, point: tuple[int, int]) -> np.ndarray:
        pass
```

**Purpose:** Transform raw data (e.g., a depth map) into a format compatible with a specific downstream model.

**Implemented by:** `SamImageAdapter`

**Contract:**
- `raw_data`: any array-like (typically a depth map)
- `image_id`: opaque string used as part of the cache key
- `point`: `(x, y)` click coordinates, also part of the cache key
- Output: 3-channel RGB `np.ndarray` suitable for SAM

---

## `IInpainter`

```python
class IInpainter(ABC):
    @abstractmethod
    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs) -> np.ndarray:
        pass
```

**Purpose:** Fill the masked region of an image with plausible background content.

**Implemented by:** `LamaInpainter`, `StableDiffusionInpainter`, `HybridInpainter`

**Contract:**
- `image`: BGR `np.ndarray`
- `mask`: binary mask (uint8 or bool); pixels > 127 (or `True`) are the area to fill
- `**kwargs`: model-specific parameters (e.g., `strength` for SD, `prompt`)
- Output: inpainted BGR `np.ndarray` of the same spatial dimensions as `image`

---

## `ISegmentationRoutingStrategy`

```python
class ISegmentationRoutingStrategy(ABC):
    @abstractmethod
    def choose_input(
        self,
        rgb_image: np.ndarray,
        raw_depth: np.ndarray,
        adapted_depth: np.ndarray,
        x: int,
        y: int,
    ) -> dict[str, Any]:
        pass
```

**Purpose:** Analyze the scene around the click and decide the optimal parameters for the SAM segmentation step.

**Implemented by:** `BoundaryVarianceRoutingStrategy`, `GradientVarianceRoutingStrategy`, `VarianceBasedRoutingStrategy`, `CenterOfMassRoutingStrategy`, `TopographicRoutingStrategy`

**Contract:**
- Inputs: RGB image, raw depth map, adapted (3-channel) depth map, click coordinates
- Output dict must contain:

| Key | Type | Description |
|---|---|---|
| `input_image` | `np.ndarray` | Image to feed to SAM (adapted depth or RGB) |
| `sd_strength` | `float` | Stable Diffusion strength passed to `HybridInpainter` |
| `use_broad_mask` | `bool` | If `True`, prefer the broader SAM mask candidate |
| `expand_pixels` | `int` | Number of pixels to dilate the mask inside the SAM facade |

---

## Adding a New Implementation

To add a new inpainter:
1. Create a class that inherits `IInpainter` and implements `inpaint()`.
2. In `ObjectRemover.__init__()`, replace `HybridInpainter()` with your class.

To add a new routing strategy:
1. Create a class that inherits `ISegmentationRoutingStrategy` and implements `choose_input()`.
2. In `ObjectRemover.__init__()`, replace `BoundaryVarianceRoutingStrategy(...)` with your class.
