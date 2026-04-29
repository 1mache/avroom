# Tests components

Scripts live in [`TestModules/tests/`](../../../TestModules/tests/) (paths relative to repo root):

| Script | Role |
|--------|------|
| `test_pipeline_runner.py` | Full removal pipeline sweep over scripted clicks + archived outputs |
| `depth_model_test.py` | Benchmark/compare depth backends under subprocess timeouts |
| `sam_masks_test.py` | Visual comparison of SAM outputs across depth variants |
| `test_trellis_reconstruction_smoke.py` | Cutout → `Reconstruction3DFacade` → GLB sanity |
| `downloadTestModelWeights.py` | Warm caches / prefetch checkpoints |

These are developer harnesses — **not** CI pytest suites.
