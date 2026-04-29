# Tests operations

## Preconditions

- GPU drivers / CUDA alignment matching [`requirements.txt`](../../../requirements.txt) torch builds when exercising heavy scripts on GPU hosts.
- HF credentials/token environment variables whenever pulling proprietary checkpoints beyond bundled SAM defaults.

## Networking

Benchmark scripts (`depth_model_test`) spawn subprocesses downloading weights unless caches warmed via `downloadTestModelWeights.py`.

## Operational posture

Expect long wall-clock durations — scripts intentionally synchronous for simplicity.

Document noteworthy regressions manually before merging inference tweaks — automated gates absent today.
