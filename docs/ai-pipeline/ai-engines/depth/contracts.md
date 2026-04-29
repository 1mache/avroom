# Depth contracts

- **Input:** BGR `np.ndarray` (H×W×3), uint8.
- **Output:** Single-channel depth map `np.ndarray`, uint8 (values treated consistently downstream as geometry proxy).

Downstream consumers do **not** receive separate near/far tensors — only the blended map leaves this domain.
