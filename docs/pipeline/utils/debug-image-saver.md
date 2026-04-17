# DebugImageSaver

**File:** `TestModules/src/utils/DebugImageSaver.py`

## Responsibility

`DebugImageSaver` is a centralized utility for writing intermediate pipeline images to disk during development and debugging. It abstracts path resolution and directory creation so that pipeline components can save debug images with a single call.

## Construction

```python
saver = DebugImageSaver(output_folder_name="outputs")
```

The output directory is resolved relative to the file's location:
- `DebugImageSaver.py` lives at `TestModules/src/utils/`
- Going up two levels reaches `TestModules/`
- The output dir is `TestModules/outputs/` (by default)

The directory is created on construction if it does not exist (`os.makedirs(..., exist_ok=True)`).

## `save(filename, image) → str`

Saves a numpy array to the configured output directory.

| Parameter | Type | Description |
|---|---|---|
| `filename` | `str` | Output filename. `.png` is appended automatically if no extension is present. |
| `image` | `np.ndarray` | Image to save. Passed directly to `cv2.imwrite`. |

**Returns:** The full filepath string if the save succeeded; empty string `""` on failure.

### Special Handling: Boolean Masks

SAM returns boolean arrays (True/False). `cv2.imwrite` writes nearly empty files for boolean arrays because it interprets `True` as 1 (nearly black). `DebugImageSaver` converts these before saving:

```python
if save_image.dtype == bool:
    save_image = (save_image * 255).astype(np.uint8)
```

### Graceful Failure

If `image` is `None` or not a numpy array, a warning is logged and an empty string is returned — the pipeline does not crash.

## Which Components Use It

| Component | Files Saved |
|---|---|
| `ObjectRemover` | `optimized_depth`, `adapted_for_sam`, `tight_mask`, `debug_tight_mask_overlay`, `mask`, `debug_mask_overlay`, `final_removed_object` |
| `SamFacadeSingleton` | `mask_0`, `mask_1`, `mask_2`, `dilated_mask`, `best_mask` |
| `HybridInpainter` | `debug_lama_output`, `debug_sd_output` |

## Output Location

All files go to `TestModules/outputs/` (gitignored). The full list of files written per pipeline run is documented in [`data-flow.md`](../../shared/data-flow.md#debug-artifacts-written-to-disk).
