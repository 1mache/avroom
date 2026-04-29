# Tests / Scripts

There is no `pytest` suite. The files under [`TestModules/tests/`](../../TestModules/tests/) are integration / benchmarking scripts that you run directly with `python`.

| File | Purpose |
|---|---|
| [`tests/test_pipeline_runner.py`](../../TestModules/tests/test_pipeline_runner.py) | Run the full `ObjectRemover.remove_object` for a fixed test image and a few hardcoded `(x, y)` points; archive outputs into per-run subfolders. |
| [`tests/depthModelTest.py`](../../TestModules/tests/depthModelTest.py) | Benchmark several Hugging Face depth models in subprocesses (with timeouts) and write each result to `TestModules/outputs/depthMaps/`. |
| [`tests/downloadTestModelWeights.py`](../../TestModules/tests/downloadTestModelWeights.py) | Warm up the HF cache by constructing pipelines for a fixed list of depth models. |
| [`tests/samMasksTest.py`](../../TestModules/tests/samMasksTest.py) | **Stale** — see below. |

## `test_pipeline_runner.py`

Walk-through:

1. `IMAGE_PATH` is hardcoded to `TestModules/inputs/test.jpg` ([line 19](../../TestModules/tests/test_pipeline_runner.py)).
2. `POINTS_TO_TEST` lists three coords (Grey Pouf, TV, Window) ([lines 21–26](../../TestModules/tests/test_pipeline_runner.py)).
3. One `ObjectRemover()` is constructed once, then `remove_object(IMAGE_PATH, x, y)` is called for each point ([lines 64–74](../../TestModules/tests/test_pipeline_runner.py)).
4. After each run, all files in `TestModules/outputs/` are moved to `outputs/script_test_outputs/<run_index>/` ([lines 38–56](../../TestModules/tests/test_pipeline_runner.py)).

Run with:

```bash
cd TestModules
python tests/test_pipeline_runner.py
```

You'll need `inputs/test.jpg` to exist; replace `POINTS_TO_TEST` with coords that match your image.

## `depthModelTest.py`

Spawns one subprocess per model in `models_to_test` (defined inside the script). Each subprocess loads the model via `ImageDepthMapper`, runs it on `inputs/test.jpg`, and saves the result under `outputs/depthMaps/<safe_model_name>.png`. Useful for picking depth backbones; not part of the API path.

## `downloadTestModelWeights.py`

Pre-warms the HF cache for the candidate depth models so subsequent runs don't pause to download. Run after a clean `git clone` if you don't want the first request through `/images/click` to take "a few minutes".

## `samMasksTest.py` — stale

This script imports `SamFacadeSingleton` and tries to call `sam.get_all_masks(adapted_image)`:

```60:60:TestModules/tests/samMasksTest.py
            masks = sam.get_all_masks(adapted_image)
```

But `SamFacadeSingleton` only defines `get_mask_at_point` — there is no `get_all_masks` method ([`SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) lines 93–121). The script will fail at runtime. It either needs the missing method added back, or the script should be removed.

## What is NOT covered by tests

- The FastAPI service ([`fastApi-app/`](../../fastApi-app/)) has no tests at all.
- The frontend ([`react-front/`](../../react-front/)) has no tests at all.
- The Python pipeline has no unit tests for individual components — only the end-to-end `test_pipeline_runner.py`.

## If you add a real test suite

A reasonable starting point would be `pytest` with:

- Unit tests for `MaskRefiner.expand_mask_uniform` (pure NumPy, deterministic).
- Unit tests for `MaskOverlapRGBAComposer.compose_original_overlap_bgra` (pure NumPy, deterministic).
- Integration tests for `ObjectRemover` with the heavy ML calls mocked at facade level.

The existing scripts can stay as smoke tests / dev tools.
