# Core contracts

## `remove_object` signature

- **`image_path`** — String path or synthetic cache key (FastAPI passes `memory://<sha256>` when bytes are supplied).
- **`x`, `y`** — Click coordinates in image pixel space.
- **`image_bytes`** — Optional raw image bytes; when set, decoding uses bytes instead of disk read.

## Return value

Tuple **`(background_bgr, cutout_bgra)`**:

| Tensor | Channels | Role |
|--------|----------|------|
| `background_bgr` | 3 (BGR) | Inpainted scene with object region replaced |
| `cutout_bgra` | 4 (BGRA) | Original pixels inside mask; alpha 0 outside mask |

Backend encodes both as PNG for HTTP responses.

## Parameters preserved but not branching

- **`depth_output_flag`** — Accepted for API compatibility; does not alter stage logic today.
