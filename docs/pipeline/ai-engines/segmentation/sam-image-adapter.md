# SamImageAdapter

**File:** `TestModules/src/ai_engines/segmentation/SamImageAdapter.py`

## Responsibility

`SamImageAdapter` adapts raw depth map data (grayscale or RGBA) into the 3-channel RGB format that SAM's predictor requires. It implements the `IImageAdapter` interface and uses composition to add caching.

## Why an Adapter Is Needed

SAM's predictor is designed for RGB images. The pipeline feeds it depth maps instead of color photos (to avoid texture-based over-segmentation). Depth maps from `OptimizedDepthFacade` are single-channel uint8 arrays. The adapter bridges this format gap.

## Adaptation Logic

```python
adapted = np.array(raw_data)

if len(adapted.shape) == 2:
    # Grayscale → RGB (replicate the single channel 3 times)
    adapted = cv2.cvtColor(adapted, cv2.COLOR_GRAY2RGB)
elif len(adapted.shape) == 3 and adapted.shape[2] == 4:
    # RGBA → RGB (drop alpha)
    adapted = cv2.cvtColor(adapted, cv2.COLOR_RGBA2RGB)
```

The result is a `(H, W, 3)` uint8 numpy array where all three channels contain the same depth intensity.

## Caching via CacheComponent

The adapter owns a `CacheComponent` instance (composition, not inheritance):

```python
self._cache = CacheComponent()
```

The cache key is a string combining `image_id` and the click point:
```python
cache_key = f"{image_id}_{point[0]}_{point[1]}"
```

On a cache hit, the stored adapted array is returned immediately without re-running the conversion. This is relevant when the user clicks multiple times on the same spot (e.g., retrying after an error) or when both the router and the main pipeline need the same adapted image.

## CacheComponent

`CacheComponent` is a minimal single-slot key-value store:

```python
class CacheComponent:
    def get(self, key: str) -> Any | None
    def set(self, key: str, data: Any)
```

Only the most recently cached entry is kept. This is sufficient for the pipeline's access pattern because each `ObjectRemover` instance processes one image at a time.

## Interface: `IImageAdapter`

```python
def get_adapted_image(self, raw_data: Any, image_id: str, point: tuple[int, int]) -> np.ndarray
```

`image_id` is typically the filesystem path of the image (as passed by `ObjectRemover`). `point` is the `(x, y)` click coordinate.
