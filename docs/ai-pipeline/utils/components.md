# Utils components

Source: [`TestModules/src/utils/`](../../../TestModules/src/utils/).

- **`MaskRefiner`** — Morphological helpers (`expand_mask_uniform`, `dilate_mask`, `expand_and_clip`).
- **`BgraCutoutComposer`** — Builds transparent cutouts preserving original textures inside masks.
- **`DebugImageSaver`** — Writes numpy arrays under `TestModules/outputs/` with `.png` extension fallback.
- **`mask_visualizer.py`** (`distinct_color`, `colorize_depth`, `overlay_masks`) — rendering helpers backing the FastAPI `/debug` endpoints ([backend/api-endpoints.md](../../backend/api-endpoints.md#debug-endpoints)), not used by the production pipeline. `distinct_color(index)` returns a deterministic BGR color via golden-ratio hue stepping (unlike the `np.random`-based coloring `TestModules/tests/sam_masks_test.py` used before this existed, colors are stable across runs). `colorize_depth(depth, colormap=None)` normalizes a depth map to uint8 (`cv2.normalize`, `NORM_MINMAX`) and returns grayscale BGR when `colormap` is `None`, else `cv2.applyColorMap`. `overlay_masks(base_bgr, masks, *, alpha=0.45, draw_outlines=True)` blends each mask over `base_bgr` in its own `distinct_color`, largest-area mask painted first so small masks stay visible on top, with a 1px white contour per mask when `draw_outlines`.
