# Ponytail Audit — Repo-Wide

Scope: over-engineering only. No bugs/security/perf. Nothing applied.

1. `delete:` OpenLRM v1.0 strategy + full vendored backend (`_backends/openlrm_v10/`, 1554 lines) — never instantiated (`Reconstruction3DFacade` only builds `Hunyuan3D2ReconstructionStrategy` primary / `TriposrReconstructionStrategy` fallback). Replacement: nothing. `TestModules/src/ai_engines/reconstruction_3d/strategies/openlrm_reconstruction_strategy.py` + `_backends/openlrm_v10/`
2. `delete:` `TrellisReconstructionStrategy` (241 lines) — imported by `Reconstruction3DFacade` but never constructed; not wired as primary or fallback. Replacement: nothing. `TestModules/src/ai_engines/reconstruction_3d/strategies/trellis_reconstruction_strategy.py`
3. `delete:` `StableZero123NovelViewStrategy` (250 lines) — is `NovelViewFacade`'s default, but the only caller (`fastApi-app/core/inference_pool/dispatch.py:132`) always passes `MeshRenderNovelViewStrategy()` explicitly, so the default is dead. Replacement: nothing (or make `MeshRenderNovelViewStrategy` the facade default and drop the param). `TestModules/src/ai_engines/novel_view/strategies/stable_zero123_novel_view_strategy.py`
4. `delete:` `Vfusion3dReconstructionStrategy` (231 lines) — imported by the facade, never constructed anywhere. Replacement: nothing. `TestModules/src/ai_engines/reconstruction_3d/strategies/vfusion3d_reconstruction_strategy.py`
5. `delete:` `CenterOfMassRoutingStrategy` (128 lines) — `SegmentationRoutingStrategy` implementation with zero callers; production always uses `BoundaryVarianceRoutingStrategy` (per CLAUDE.md). Replacement: nothing. `TestModules/src/routing/strategies/center_of_mass_routing_strategy.py`
6. `yagni:` `CompositeContentValidationStrategy` (46 lines, N-way merge-and-vote machinery) is only ever constructed with a 1-element tuple, both in the facade default and the one test that touches it — `ContentValidationFacade` could call `ClipZeroShotContentValidationStrategy()` directly. Replacement: `ClipZeroShotContentValidationStrategy()`. `TestModules/src/ai_engines/content_validation/content_validation_facade.py`, `strategies/composite_content_validation_strategy.py`

Also dead: `TestModules/tests/test_vfusion3d_hub_load.py`, `TestModules/tests/test_trellis_reconstruction_smoke.py` — tests for #2/#4, remove alongside.

Checked and NOT flagged: `camera_calibration` (geocalib) and `elevation_estimation` (geometric) are single-implementation Facade/Strategy pairs, but both are live production callers, not speculative — consistent with the project's deliberate per-AI-engine Facade+Strategy convention (CLAUDE.md), so left alone.

net: -2610 lines, -0 deps possible (all in-repo, no package removal).
