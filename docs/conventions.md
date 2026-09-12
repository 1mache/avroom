# Conventions and Design Patterns

Project-wide patterns and rules-of-thumb to keep in mind when reading or extending the code.

## Domain language

User-facing nouns and verbs (Room, Origin Photo, Cutout, Copy, Object Selector, …) are defined in [`CONTEXT.md`](../CONTEXT.md). Prefer those words in docs and discussion. Code identifiers (`session`, `uid`, `ObjectRail`, `glbData`) stay as they are in source.

## Architectural patterns in use

The AI pipeline leans on a strict Facade + Strategy split per AI domain; the web tiers stay deliberately thin.

| Pattern | Where | Why |
|---|---|---|
| **Master Facade** | [`ObjectRemover`](../ai-pipeline/src/core/object_remover.py) | Single-call entry point that composes one Facade per AI domain plus a routing strategy. |
| **Domain Facade** | [`DepthMappingFacade`](../ai-pipeline/src/ai_engines/depth/depth_mapping_facade.py), [`ImageSegmentationFacade`](../ai-pipeline/src/ai_engines/segmentation/image_segmentation_facade.py), [`ImageInpaintingFacade`](../ai-pipeline/src/ai_engines/inpainting/image_inpainting_facade.py), [`NovelViewFacade`](../ai-pipeline/src/ai_engines/novel_view/novel_view_facade.py), [`Reconstruction3DFacade`](../ai-pipeline/src/ai_engines/reconstruction_3d/reconstruction_3d_facade.py), [`CameraCalibrationFacade`](../ai-pipeline/src/ai_engines/camera_calibration/camera_calibration_facade.py), [`ElevationEstimationFacade`](../ai-pipeline/src/ai_engines/elevation_estimation/elevation_estimation_facade.py) | Each Facade owns exactly one Strategy and gives client code a stable surface that doesn't change when the strategy is swapped. |
| **Strategy** | `DepthMappingStrategy`, `ImageSegmentationStrategy`, `ImageInpaintingStrategy`, `NovelViewStrategy`, `Reconstruction3DStrategy`, `CameraCalibrationStrategy`, `ElevationEstimationStrategy`, `SegmentationRoutingStrategy` (ABCs) | Make the "which model / which algorithm" decision pluggable. The concrete strategies live under each domain's `strategies/` folder. |
| **Composite Strategy** | [`HybridInpaintingStrategy`](../ai-pipeline/src/ai_engines/inpainting/strategies/hybrid_inpainting_strategy.py), [`NearFarBlendedDepthMappingStrategy`](../ai-pipeline/src/ai_engines/depth/strategies/near_far_blended_depth_mapping_strategy.py) | Composes other Strategy instances of the same ABC (LaMa+SD; near + far depth) — the composition itself is a Strategy. |
| **Adapter** | [`SamImageAdapter`](../ai-pipeline/src/ai_engines/segmentation/sam_image_adapter.py) | Convert single-channel depth into the 3-channel RGB SAM expects. |
| **Dependency injection with sensible defaults** | [`ObjectRemover.__init__`](../ai-pipeline/src/core/object_remover.py) lines 64–92 | Every collaborator is injected via the constructor with a default fallback. `ObjectRemover()` still works without arguments. |
| **Lazy load via `functools.lru_cache`** | `_load_depth_pipeline`, `_load_sam_predictor`, `_load_simple_lama`, `_load_stable_diffusion_pipe` | Models are expensive to load; cache them once per process behind a module-level factory. **Replaces the old class-level Singletons** — the strategy classes themselves are plain objects. |
| **Composition over inheritance** | `SamSegmentationStrategy` owns a `MaskRefiner`; `SamImageAdapter` owns a `_SingleEntryCache` | Functionality is added by holding helper objects, not subclassing them. |

## Interface contracts (Strategy ABCs)

There is no longer a single `interfaces.py` — each AI domain owns its own ABC alongside its Facade:

- [`DepthMappingStrategy.map_depth(image) -> ndarray`](../ai-pipeline/src/ai_engines/depth/depth_mapping_strategy.py)
- [`ImageSegmentationStrategy.predict_mask(image, x, y, *, expand_pixels, use_broad_mask) -> tuple[ndarray, ndarray]`](../ai-pipeline/src/ai_engines/segmentation/image_segmentation_strategy.py) — returns `(expanded_mask, original_mask)`; `original_mask` is the raw SAM output, `expanded_mask` is that mask after any `expand_pixels` dilation (or a copy when `expand_pixels == 0`).
- [`ImageInpaintingStrategy.inpaint(image, mask, **kwargs) -> ndarray`](../ai-pipeline/src/ai_engines/inpainting/image_inpainting_strategy.py)
- [`NovelViewStrategy.synthesize(image, *, elevation_deg, azimuth_deg, ...) -> ndarray`](../ai-pipeline/src/ai_engines/novel_view/novel_view_strategy.py)
- [`Reconstruction3DStrategy.generate(image, *, quality, output, output_path, seed) -> bytes | Path | BinaryIO`](../ai-pipeline/src/ai_engines/reconstruction_3d/reconstruction_3d_strategy.py)
- [`CameraCalibrationStrategy.calibrate(image) -> CameraCalibrationResult`](../ai-pipeline/src/ai_engines/camera_calibration/camera_calibration_strategy.py)
- [`ElevationEstimationStrategy.estimate(depth, mask, *, calibration) -> ElevationEstimationResult`](../ai-pipeline/src/ai_engines/elevation_estimation/elevation_estimation_strategy.py)
- [`SegmentationRoutingStrategy.choose_input(rgb_image, raw_depth, adapted_depth, x, y) -> dict`](../ai-pipeline/src/routing/segmentation_routing_strategy.py)

Every concrete strategy in this package implements exactly one of these.

## Critical AI lessons baked into the code

These are things that look weird but should NOT be "simplified":

- **SAM is fed depth, not RGB.** RGB causes SAM to over-segment along texture/fabric/shadow seams. The adapted depth map gives clean geometric boundaries. See [`sam_image_adapter.py`](../ai-pipeline/src/ai_engines/segmentation/sam_image_adapter.py) and the `input_image: adapted_depth` choice in [`boundary_variance_routing_strategy.py`](../ai-pipeline/src/routing/strategies/boundary_variance_routing_strategy.py) line 105.
- **Two depth models, alpha-blended.** V2 Small is good for the foreground (near), LiheYoung Small is good for far walls. Hard switching causes visible seams; alpha compositing using the near map's confidence avoids them. See [`near_far_blended_depth_mapping_strategy.py`](../ai-pipeline/src/ai_engines/depth/strategies/near_far_blended_depth_mapping_strategy.py) lines 49–66.
- **Small mask refine before inpainting; larger growth is routing + verifier.**
  Attempt 0 expands via routing ``expand_pixels`` (~4–20 on BoundaryVariance;
  image pass fixed 14), then ~3 px via
  [`MaskRefiner.expand_mask_uniform`](../ai-pipeline/src/utils/mask_refiner.py).
  On verify fail, Hybrid may apply ``mask_dilate_pixels`` /
  ``compose_dilate_pixels``. Always sanitize before dilating (bridges SAM speckles).
- **LaMa is given a mean-fill mask interior.** Before passing the image to LaMa, the masked region is replaced with the mean color of its boundary so LaMa is not biased by the object's own pixels. See [`lama_inpainting_strategy.py`](../ai-pipeline/src/ai_engines/inpainting/strategies/lama_inpainting_strategy.py) lines 52–66.
- **SD is skipped at low strength.** When `sd_strength <= 0.2` the hybrid uses the primary (LaMa) result only ([`hybrid_inpainting_strategy.py`](../ai-pipeline/src/ai_engines/inpainting/strategies/hybrid_inpainting_strategy.py) lines 70–72) — SD's 512² resize introduces smear that you don't want for already-good LaMa output.

If you change any of the above, expect mask bleed, halos, or hallucinations to come back.

## Naming conventions

- File and directory names are `snake_case` throughout `ai-pipeline/src/`. Class names are `PascalCase`.
- Per-domain layout: `<domain>_facade.py` for the Facade, `<domain>_strategy.py` for the ABC, and `strategies/<concrete>_<domain>_strategy.py` for concrete strategies (e.g. `lama_inpainting_strategy.py`, `sam_segmentation_strategy.py`).
- Public packages are imported as `avroom_object_removal.*` even though the source is under `ai-pipeline/src/`. The remap is in [`ai-pipeline/pyproject.toml`](../ai-pipeline/pyproject.toml) lines 35–36 (`[tool.setuptools.package-dir]`).
- Frontend components use `PascalCase.tsx`, hooks/utilities `camelCase.ts`.

## Debug artifacts

Every pipeline run writes a constellation of PNGs to `ai-pipeline/outputs/` via [`DebugImageSaver`](../ai-pipeline/src/utils/debug_image_saver.py) and the SAM strategy. See [ai-pipeline/core/README.md](ai-pipeline/core/README.md) for output artifact coverage. The backend writes its own debug image at `{storage_dir}/point/{image_id}_debug.png` ([`image_processing.py`](../fastApi-app/core/image_processing.py) lines 33–51) showing the click marker on the input.

These are intentionally left around — they're the project's primary debugging tool.

## Logging

Every Python module declares a module-level `logger = logging.getLogger(__name__)`. The FastAPI service uses a central logging config in [`fastApi-app/logging_config.py`](../fastApi-app/logging_config.py) and calls `setup_logging()` once in [`fastApi-app/main.py`](../fastApi-app/main.py) line 14.

## Testing posture

There is no `pytest` suite. The integration script [`ai-pipeline/tests/test_pipeline_runner.py`](../ai-pipeline/tests/test_pipeline_runner.py) exercises the full pipeline against `ai-pipeline/inputs/test.jpg` for hardcoded points and archives results under `outputs/script_test_outputs/<run>`. Other scripts in `ai-pipeline/tests/` are model warm-up / benchmarking helpers. See [ai-pipeline/tests/README.md](ai-pipeline/tests/README.md).
