# Reconstruction 3D operations

## Space identifier

Default HF Space id carried by `TrellisReconstructionStrategy` (see source constant, commonly `microsoft/TRELLIS.2`).

## Quality presets

Each preset adjusts synthetic mesh fidelity vs latency trade-offs — inspect `PRESETS` dict for numeric fields.

## Operational realities

- Remote Space queues introduce variable latency unrelated to local GPU availability.
- Failures raise **`Trellis3DGenerationError`** — callers must handle absence of GLB bytes.

## Authentication

Optional HF token wiring enables authenticated Space clients — consult strategy constructor parameters.
