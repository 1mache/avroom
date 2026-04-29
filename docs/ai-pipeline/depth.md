# Depth Estimation

Two files, one for the singleton wrapper around HuggingFace pipelines and one for the alpha-blended facade that the orchestrator actually calls.

## `ImageDepthMapper`

[`TestModules/src/ai_engines/depth/ImageDepthMapper.py`](../../TestModules/src/ai_engines/depth/ImageDepthMapper.py)

Singleton facade over `transformers.pipeline(task="depth-estimation", model=...)`. The model can be hot-swapped via the `model` property; setting a new model rebuilds the underlying pipeline:

```51:57:TestModules/src/ai_engines/depth/ImageDepthMapper.py
    @model.setter
    def model(self, new_model: str) -> None:
        """Change the model and rebuild the pipeline if different."""
        if new_model != self._model_name:
            logger.info(f"Switching model from {self._model_name} to {new_model}")
            self._model_name = new_model
            self._create_pipeline()
```

Default model on first construction:

```30:30:TestModules/src/ai_engines/depth/ImageDepthMapper.py
        self._model_name = "LiheYoung/depth-anything-small-hf"
```

`get_depth_map(image)` accepts either a numpy array or a PIL image and returns the `depth` PIL image from the HF pipeline.

## `OptimizedDepthFacade`

[`TestModules/src/ai_engines/depth/OptimizedDepthFacade.py`](../../TestModules/src/ai_engines/depth/OptimizedDepthFacade.py) — the only thing the orchestrator talks to.

```6:38:TestModules/src/ai_engines/depth/OptimizedDepthFacade.py
class OptimizedDepthFacade(IDepthFacade):
    """
    Facade that uses Soft Blending to merge Near and Far models smoothly.
    Returns a clean, un-tampered depth map for optimal data fusion.
    """
    def __init__(self, threshold: int = 100):
        self.depth_mapper = ImageDepthMapper()
        self.threshold = threshold

    def get_optimized_depth_map(self, image: np.ndarray) -> np.ndarray:
        # 1. Generate Near-Field Map (V2)
        self.depth_mapper.model = "depth-anything/Depth-Anything-V2-Small-hf"
        depth_v2 = np.array(self.depth_mapper.get_depth_map(image))
        if len(depth_v2.shape) == 3:
            depth_v2 = cv2.cvtColor(depth_v2, cv2.COLOR_RGB2GRAY)

        # 2. Generate Far-Field Map (Lihe)
        self.depth_mapper.model = "LiheYoung/depth-anything-small-hf"
        depth_lihe = np.array(self.depth_mapper.get_depth_map(image))
        if len(depth_lihe.shape) == 3:
            depth_lihe = cv2.cvtColor(depth_lihe, cv2.COLOR_RGB2GRAY)

        # 3. Soft blend (alpha compositing):
        # - depth_v2 contributes more where its normalized confidence is high.
        # - depth_lihe contributes more where depth_v2 is weaker.
        # This avoids hard seams between near-field and far-field behaviors.
        depth_v2_norm = cv2.normalize(depth_v2, None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)
        depth_lihe_norm = cv2.normalize(depth_lihe, None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)
        
        alpha = depth_v2_norm / 255.0
        optimized_depth = (depth_v2_norm * alpha) + (depth_lihe_norm * (1.0 - alpha))
        
        return optimized_depth.astype(np.uint8)
```

### What it does

1. Run the V2 Small model — good for foreground / near.
2. Run the LiheYoung Small model — good for background / far walls.
3. Normalize both to `[0, 255]` floats.
4. Use the V2 normalized depth as the alpha channel: `out = v2 * alpha + lihe * (1 - alpha)`.

The end result is a uint8 grayscale where bright = near, dark = far, with smooth blending instead of a hard handoff between the two models.

### Why two models

This is one of the project's "do not touch" lessons (also noted in [../conventions.md](../conventions.md)):

- A single depth model leaves either close-up objects fuzzy (LiheYoung) or far walls noisy (V2).
- Hard switching between them produces visible seams.
- Alpha blending using V2 confidence keeps each model's strength in their region.

### Quirks

- `OptimizedDepthFacade.__init__` accepts a `threshold` kwarg and stores it on `self`, but `get_optimized_depth_map` does not reference it. It's effectively dead at the moment.
- Because `ImageDepthMapper` is a singleton, two instances of `OptimizedDepthFacade` share the underlying pipeline and **mutate each other's `model`** when they call `get_optimized_depth_map`. This is fine in the current single-`ObjectRemover`-per-call model but worth keeping in mind if you ever introduce parallelism.
- Cost: each call runs **both** depth models, so the depth stage is the second-heaviest after SD. For a CPU run, this dominates wall-clock time.

## Output

The orchestrator saves the blended depth to `outputs/optimized_depth.png` ([`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 89). It is fed into [`SamImageAdapter`](../../TestModules/src/ai_engines/segmentation/SamImageAdapter.py) and ultimately into SAM as RGB.
