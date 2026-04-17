# End-to-End Data Flow

This document traces a single user session from image upload to receiving results.

## Step 1 — Upload

```
User selects file
      │
      ▼
UploadFrame (react-front)
      │  POST /images/upload  (multipart/form-data)
      ▼
FastAPI  routes.py :: upload_image()
      │  generates uuid → saves to fastApi-app/images/<uuid>.<ext>
      ▼
Response: { image_id, original_filename, stored_path }
      │
      ▼
MainPage stores image_id in state
```

## Step 2 — Click Selection

```
User clicks on the displayed image
      │
      ▼
UploadFrame :: handleContainerClick()
      │  converts display-pixel coords → natural (original-resolution) pixel coords
      │  using img.naturalWidth / img.naturalHeight ratio
      ▼
MainPage stores naturalClickPos { x, y }
```

## Step 3 — Run (Click Processing)

```
User presses "Run"
      │
      ▼
MainPage :: handleRun()
      │  POST /images/click  { image_id, x, y }
      ▼
FastAPI  routes.py :: handle_click()
      │
      ▼
core/image_processing.py :: process_click_on_image()
      │  1. Resolves file path for image_id on disk
      │  2. Saves a debug overlay image (red dot at click coords) → images/tmp/
      │
      ▼
core/image_processing.py :: segment_at_click()
      │  1. Patches sys.path and sys.modules to expose TestModules/src as top-level packages
      │     (avoids name collision with fastApi-app's own `core` package)
      │  2. Saves image bytes as a temp PNG for cv2 compatibility
      │  3. Constructs ObjectRemover()
      │  4. Calls remover.remove_object(image_path, x, y)
      │  5. Encodes numpy arrays back to PNG bytes
      │  6. Restores sys.modules to its original state
      │
      ▼
TestModules/src/core/objectRemover.py :: ObjectRemover.remove_object()
      │
      │  [PIPELINE — see below]
      │
      ▼
Returns: background_bytes (PNG), cutout_bytes (PNG), format="png"
      │
      ▼
routes.py :: handle_click()
      │  base64-encodes both byte strings
      ▼
Response: { image_id, background_b64, cutout_b64, format }
      │
      ▼
MainPage
      │  builds data URLs: "data:image/png;base64,<b64>"
      ▼
ResultFrame "Background"  +  ResultFrame "Cutout"  rendered in UI
```

## Step 4 — Internal ML Pipeline (ObjectRemover)

```
image (BGR numpy)  +  click (x, y)
      │
      ▼
1. OptimizedDepthFacade.get_optimized_depth_map(image)
      │  Runs V2 model (near)  +  LiheYoung model (far)
      │  Alpha-composites both: alpha = V2_depth_normalized
      │  Returns: uint8 grayscale depth map
      │
      ▼
2. SamImageAdapter.get_adapted_image(depth, image_id, point)
      │  Converts grayscale depth → 3-channel RGB (SAM input format)
      │  Checks CacheComponent; returns cached result if same image_id+point
      │
      ▼
3. BoundaryVarianceRoutingStrategy.choose_input(rgb, raw_depth, adapted_depth, x, y)
      │  Probes SAM with a zero-expand mask at (x, y)
      │  Extracts a 7px boundary ring around the probe mask
      │  Computes depth variance on that ring
      │  High variance → 3D object  |  Low variance → flat surface
      │  Returns: run_context { input_image, sd_strength, use_broad_mask, expand_pixels }
      │
      ▼
4. SamFacadeSingleton.get_mask_at_point(run_context.input_image, x, y, expand_pixels)
      │  Sets image on SAM predictor
      │  Runs multimask prediction; selects masks[1] (tight mask)
      │  Dilates by expand_pixels using MaskRefiner.dilate_mask()
      │  Returns: binary mask (uint8 HxW)
      │
      ▼
5. MaskRefiner.expand_mask_uniform(tight_mask, radius=3)
      │  Symmetric 3px dilation in all directions
      │  Extra 2px downward bias (to catch object bases)
      │  Returns: refined mask
      │
      ▼
6. HybridInpainter.inpaint(image, mask, strength=run_context.sd_strength)
      │  Phase 1: LamaInpainter.inpaint()
      │    - Fills mask region with boundary mean color
      │    - Runs SimpleLama; returns BGR result
      │  Phase 2 (if strength > 0.2): StableDiffusionInpainter.inpaint()
      │    - Resizes to 512×512, runs SD pipeline, resizes back
      │  Post-processing:
      │    - Unsharp sharpening (sigma=0.8, factor=0.6)
      │    - Interior color nudge toward boundary mean (0.35 factor)
      │  Returns: inpainted background (BGR)
      │
      ▼
7. MaskOverlapRGBAComposer.compose_original_overlap_bgra(original, mask)
      │  Creates BGRA image with alpha=255 only inside the mask
      │  Returns: cutout (BGRA)
      │
      ▼
Output: (background_bgr, cutout_bgra)
```

## Debug Artifacts Written to Disk

During every `remove_object` call, `DebugImageSaver` writes intermediate images to `TestModules/outputs/`:

| Filename | Content |
|---|---|
| `optimized_depth.png` | Blended depth map after step 1 |
| `adapted_for_sam.png` | 3-channel depth used as SAM input |
| `tight_mask.png` | Raw SAM mask before uniform expansion |
| `debug_tight_mask_overlay.png` | Original image with tight mask area painted white |
| `mask.png` | Refined mask after `expand_mask_uniform` |
| `debug_mask_overlay.png` | Original image with final mask painted white |
| `debug_lama_output.png` | LaMa result before SD pass |
| `debug_sd_output.png` | Final inpainted result |
| `final_removed_object.png` | Same as `debug_sd_output` |
| `mask_0/1/2.png` | All three SAM candidate masks |
| `dilated_mask.png` | SAM mask after `dilate_mask` inside the facade |
| `best_mask.png` | Chosen SAM mask after dilation |
