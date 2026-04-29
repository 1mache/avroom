# Conventions and Design Patterns

Project-wide patterns and rules-of-thumb to keep in mind when reading or extending the code.

## Architectural patterns in use

The AI pipeline leans heavily on classic OO patterns; the web tiers stay deliberately thin.

| Pattern | Where | Why |
|---|---|---|
| **Facade** | [`OptimizedDepthFacade`](../TestModules/src/ai_engines/depth/OptimizedDepthFacade.py), [`SamFacadeSingleton`](../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py), [`LamaInpainter`](../TestModules/src/ai_engines/inpainting/LamaInpainter.py), [`StableDiffusionInpainter`](../TestModules/src/ai_engines/inpainting/StableDiffusionInpainter.py) | Hide the heavy ML library underneath a small, project-specific surface. |
| **Singleton** | `ImageDepthMapper`, `SamFacadeSingleton`, `LamaInpainter`, `ImageAdapterFactory` | Models are expensive to load; only one instance allowed. Pattern is implemented via `__new__` + `_initialized` guards. |
| **Adapter** | [`SamImageAdapter`](../TestModules/src/ai_engines/segmentation/SamImageAdapter.py) | Convert single-channel depth into the 3-channel RGB SAM expects. |
| **Strategy** | [`ISegmentationRoutingStrategy`](../TestModules/src/core/interfaces.py) + the five `*RoutingStrategy` classes in [`routing/`](../TestModules/src/routing/) | Make the "how should we feed SAM here?" decision pluggable. Production uses [`BoundaryVarianceRoutingStrategy`](../TestModules/src/routing/boundary_variance_strategy.py). |
| **Composite / Chain** | [`HybridInpainter`](../TestModules/src/ai_engines/inpainting/HybridInpainter.py) | LaMa first (structural), then optional SD refinement, then unsharp + boundary color nudge. |
| **Composition over inheritance** | `SamFacadeSingleton` owns a `MaskRefiner`; `SamImageAdapter` owns a `CacheComponent` | Functionality is added by holding helper objects, not subclassing them. |

## Interface contracts

[`TestModules/src/core/interfaces.py`](../TestModules/src/core/interfaces.py) is the source of truth:

- `IDepthFacade.get_optimized_depth_map(image) -> ndarray`
- `IImageAdapter.get_adapted_image(raw_data, image_id, point) -> ndarray`
- `IInpainter.inpaint(image, mask, **kwargs) -> ndarray`
- `ISegmentationRoutingStrategy.choose_input(rgb_image, raw_depth, adapted_depth, x, y) -> dict`

All concrete classes that participate in the pipeline implement one of these, except the SAM facade which is held under its own concrete type.

## Critical AI lessons baked into the code

These are things that look weird but should NOT be "simplified":

- **SAM is fed depth, not RGB.** RGB causes SAM to over-segment along texture/fabric/shadow seams. The adapted depth map gives clean geometric boundaries. See [`SamImageAdapter.py`](../TestModules/src/ai_engines/segmentation/SamImageAdapter.py) and the `input_image: adapted_depth` choice in [`boundary_variance_strategy.py`](../TestModules/src/routing/boundary_variance_strategy.py) line 74.
- **Two depth models, alpha-blended.** V2 Small is good for the foreground (near), LiheYoung Small is good for far walls. Hard switching causes visible seams; alpha compositing using V2 confidence avoids them. See [`OptimizedDepthFacade.py`](../TestModules/src/ai_engines/depth/OptimizedDepthFacade.py) lines 15–38.
- **Mask is dilated before inpainting.** A perfectly tight SAM mask makes LaMa/SD bleed object pixels into the background. The pipeline expands by ~3px uniformly via [`MaskRefiner.expand_mask_uniform`](../TestModules/src/utils/MaskRefiner.py) lines 57–81 plus a downward bias.
- **LaMa is given a mean-fill mask interior.** Before passing the image to LaMa, the masked region is replaced with the mean color of its boundary so LaMa is not biased by the object's own pixels. See [`LamaInpainter.py`](../TestModules/src/ai_engines/inpainting/LamaInpainter.py) lines 41–52.
- **SD is skipped at low strength.** When `sd_strength <= 0.2` the hybrid uses LaMa only ([`HybridInpainter.py`](../TestModules/src/ai_engines/inpainting/HybridInpainter.py) lines 53–56) — SD's 512² resize introduces smear that you don't want for already-good LaMa output.

If you change any of the above, expect mask bleed, halos, or hallucinations to come back.

## Naming conventions

- Class files mirror class names (e.g. `OptimizedDepthFacade.py` defines `OptimizedDepthFacade`). Mostly PascalCase filenames in `ai_engines/` and `utils/`, snake_case in `routing/`.
- Public packages are imported as `avroom_object_removal.*` even though the source is under `TestModules/src/`. The remap is in [`TestModules/pyproject.toml`](../TestModules/pyproject.toml) line 23 (`[tool.setuptools.package-dir]`).
- Frontend components use `PascalCase.tsx`, hooks/utilities `camelCase.ts`.

## Debug artifacts

Every pipeline run writes a constellation of PNGs to `TestModules/outputs/` via [`DebugImageSaver`](../TestModules/src/utils/DebugImageSaver.py) and the SAM facade. Full list in [ai-pipeline/outputs.md](ai-pipeline/outputs.md). The backend writes its own debug image at `{storage_dir}/tmp/{image_id}_debug.png` ([`image_processing.py`](../fastApi-app/core/image_processing.py) lines 32–50) showing the click marker on the input.

These are intentionally left around — they're the project's primary debugging tool.

## Logging

Every Python module declares a module-level `logger = logging.getLogger(__name__)`. There is no central logging config; the API server uses uvicorn's defaults, and the test scripts call `logging.basicConfig` ad hoc.

## Testing posture

There is no `pytest` suite. The integration script [`TestModules/tests/test_pipeline_runner.py`](../TestModules/tests/test_pipeline_runner.py) exercises the full pipeline against `TestModules/inputs/test.jpg` for hardcoded points and archives results under `outputs/script_test_outputs/<run>`. Other scripts in `TestModules/tests/` are model warm-up / benchmarking helpers. See [ai-pipeline/tests.md](ai-pipeline/tests.md).
