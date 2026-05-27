# Core contracts

## `ObjectRemover.remove_object`

**Signature:** `remove_object(image_path, x, y, depth_output_flag=False, image_bytes=None)`

- **`image_path`** — String path or synthetic cache key (FastAPI passes `memory://<sha256>` when bytes are supplied).
- **`x`, `y`** — Click coordinates in image pixel space.
- **`image_bytes`** — Optional raw image bytes; when set, decoding uses bytes instead of disk read.
- **`depth_output_flag`** — Accepted for API compatibility; does not alter stage logic today.

**Returns** `(background_bgr, cutout_bgra)`:

| Tensor | Channels | Role |
|--------|----------|------|
| `background_bgr` | 3 (BGR) | Inpainted scene with object region replaced |
| `cutout_bgra` | 4 (BGRA) | Original pixels inside raw SAM mask; alpha 0 outside |

Backend encodes both as PNG for HTTP responses.

---

## `ObjectSegmentor.get_mask_for_object_at_position`

**Signature:** `get_mask_for_object_at_position(image_path, x, y, image_bytes=None)`

- **`image_path`** — String path or synthetic cache key.
- **`x`, `y`** — Click coordinates in image pixel space.
- **`image_bytes`** — Optional raw image bytes.

**Returns** `tuple[tuple[np.ndarray, np.ndarray], ...]` — one pair per SAM candidate:

| Position | Tensor | Channels | Role |
|----------|--------|----------|------|
| `[i][0]` | `refined_mask` | 1 (uint8 0/255) | Routing-expanded mask after 3 px uniform dilation; ready for inpainting |
| `[i][1]` | `cutout_bgra` | 4 (BGRA) | Original pixels inside the raw SAM mask; alpha 0 outside |

Typically 3 pairs (SAM's three multimask candidates). Inpainting is not performed.

---

## `BackgroundInpainter.cut_mask_from_image`

**Signature:** `cut_mask_from_image(original_image, mask)`

- **`original_image`** — BGR `np.ndarray` of the full scene.
- **`mask`** — Binary 2-D mask (0 / 255). Typically a `refined_mask` from `ObjectSegmentor`.

**Returns** `result_image` — BGR `np.ndarray`, same spatial size as `original_image`, with the masked region filled by the inpainting model.
