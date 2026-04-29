# Utils contracts

- **`MaskRefiner.expand_mask_uniform`** — Consumes binary-ish mask + radius + directional bias constants; yields expanded mask equal shape input.
- **`BgraCutoutComposer.compose_original_overlap_bgra`** — Consumes original BGR tensor plus refined mask; returns uint8 BGRA tensor aligned spatially.
- **`DebugImageSaver.save(stem, array)`** — Accepts ndarray; filenames persist relative to configured outputs directory.

Unused pathways (`expand_and_clip`) remain callable but orchestrator omits them — depth tolerance knob dormant unless explicitly wired later.
