# Normal mapping contracts

- **Input:** BGR `np.ndarray` (H×W×3), uint8.
- **Output:** Camera-frame unit normals `np.ndarray`, `float32` (H×W×3), channels `(nx, ny, nz)`.

Depth from Metric3D is intentionally not part of this engine’s contract.
