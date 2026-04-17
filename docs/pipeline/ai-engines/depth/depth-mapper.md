# ImageDepthMapper

**File:** `TestModules/src/ai_engines/depth/ImageDepthMapper.py`

## Responsibility

`ImageDepthMapper` is a singleton wrapper around the HuggingFace `transformers.pipeline` for depth estimation. It manages a single in-memory pipeline instance and rebuilds it only when the model or task changes.

## Singleton Behavior

`ImageDepthMapper` uses `__new__` to ensure only one instance exists per process. The `_initialized` flag prevents re-running `__init__` on subsequent calls to the constructor:

```python
mapper = ImageDepthMapper()  # First call: loads model
mapper2 = ImageDepthMapper() # Same instance, no reload
```

The default model on first initialization is `LiheYoung/depth-anything-small-hf`.

## Public API

### `get_depth_map(image, output_path=None) → PIL.Image`

Runs the depth estimation pipeline on the input.

| Parameter | Type | Description |
|---|---|---|
| `image` | `np.ndarray` or `PIL.Image` | Input image. numpy arrays are converted to PIL automatically. |
| `output_path` | `str \| None` | If provided, saves the resulting depth map to this path. |

Returns a PIL Image containing the grayscale depth map (brighter = closer, typically).

### `model` property (read/write)

Gets or sets the HuggingFace model identifier. Setting a new value triggers a pipeline rebuild:

```python
mapper.model = "depth-anything/Depth-Anything-V2-Small-hf"
# Pipeline is rebuilt immediately with the new model
```

### `task` property (read/write)

Gets or sets the pipeline task string (default: `"depth-estimation"`). Changing it also rebuilds the pipeline.

## How It Is Used

`OptimizedDepthFacade` uses `ImageDepthMapper` by switching its model property twice in sequence:

```python
self.depth_mapper.model = "depth-anything/Depth-Anything-V2-Small-hf"
depth_v2 = self.depth_mapper.get_depth_map(image)

self.depth_mapper.model = "LiheYoung/depth-anything-small-hf"
depth_lihe = self.depth_mapper.get_depth_map(image)
```

Because `ImageDepthMapper` is a singleton, both calls share the same instance; the pipeline is rebuilt between the two calls. See [`optimized-depth-facade.md`](optimized-depth-facade.md).
