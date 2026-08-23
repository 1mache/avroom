# Tests components

Scripts live in [`TestModules/tests/`](../../../TestModules/tests/) (paths relative to repo root):

| Script | Role |
|--------|------|
| `test_pipeline_runner.py` | Full removal pipeline sweep over scripted clicks + archived outputs |
| `depth_model_test.py` | Benchmark/compare depth backends under subprocess timeouts |
| `sam_masks_test.py` | Visual comparison of SAM outputs across depth variants |
| `test_trellis_reconstruction_smoke.py` | Cutout → `Reconstruction3DFacade(TrellisReconstructionStrategy())` → GLB sanity for the optional Trellis backend (facade **defaults to Hunyuan3D-2.1** with automatic TripoSR fallback when constructed with no strategy — this script explicitly injects Trellis instead) |
| `test_vfusion3d_hub_load.py` | Weight-load sanity for the optional VFusion3D backend |
| `downloadTestModelWeights.py` | Warm caches / prefetch checkpoints |

These are developer harnesses — **not** CI pytest suites.
