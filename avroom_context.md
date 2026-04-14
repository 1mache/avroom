# Avroom - Project Context & Architecture

**Project Goal:** An AI-powered application to accurately select and remove objects/furniture from room images and naturally inpaint the missing background.

## 🛠️ Tech Stack

- **Language:** Python 3.x
- **Computer Vision:** OpenCV (`cv2`), Numpy, PIL
- **AI Models (HuggingFace):** \* **Segmentation:** Segment Anything Model (SAM) - `sam_vit_b_01ec64.pth`
  - **Inpainting:** LaMa (Large Mask Inpainting)
  - **Depth Estimation:** `depth-anything/Depth-Anything-V2-Small-hf` (Near) + `LiheYoung/depth-anything-small-hf` (Far)

## 🏗️ Architecture & Design Patterns

The system uses a highly modular architecture based on SOLID principles, utilizing structural design patterns:

1. **`ObjectRemover` (Controller / Main Facade):** Orchestrates the entire pipeline. Receives the image and coordinates, and passes them through the depth, segmentation, and inpainting modules.
2. **`SamFacadeSingleton` (Singleton + Facade):** Ensures the heavy SAM model is loaded into memory only once. Hides the complexity of HuggingFace predictors.
3. **`OptimizedDepthFacade` (Facade):** Encapsulates the complex math required to solve the "Near-Far Problem" by generating two depth maps and blending them.
4. **`SamImageAdapter` (Adapter):** Converts 1-channel Grayscale depth maps into the 3-channel RGB format required by SAM.
5. **`MaskRefiner` (Utility / Composition):** Handled post-processing of SAM masks (Morphological operations). Composed inside the SamFacade.
6. **`CacheComponent` (Composition):** Used inside the Adapter to cache adapted images for faster re-clicks.

## 🧠 Critical AI Logic & Lessons Learned (DO NOT CHANGE)

- **The Near-Far Depth Blending:** We use _Alpha Compositing_ (Soft Blending) to merge the V2 model (good for foreground/near) with the LiheYoung model (good for background/far walls). V2's depth values serve as the Alpha weight. This prevents sharp artificial seams on walls.
- **Over-segmentation Prevention (Why SAM uses Depth only):** SAM is highly sensitive to fabric creases, shadows, and textures (causing it to segment only parts of a sofa, for example). Therefore, **we feed SAM the pure, smooth 3-channel depth map** (via Adapter), NOT the original RGB image. This gives SAM perfect geometric boundaries without texture distractions.
- **Halo Effect Prevention (Mask Dilation):** LaMa tends to bleed object pixels into the background if the mask is perfectly tight. We use `MaskRefiner.dilate_mask(pixels=8)` to expand the mask morphology by default, forcing LaMa to sample from true background pixels only.

## 📁 Directory Structure

- `models/` or `checkpoints/` - Contains `.pth` weights for SAM.
- `inputs/` - Source images for testing.
- `outputs/` - Results (including intermediate steps like `mask.png`, `optimized_depth.png`, `adapted_for_sam.png`).
- `src/` - Contains all architectural Python files (`ObjectRemover.py`, `OptimizedDepthFacade.py`, `MaskRefiner.py`, etc.).
