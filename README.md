# Avroom Object Remover - Core Engine Architecture

## Overview

The `ObjectRemover` is an advanced, **context-aware** inpainting pipeline designed to seamlessly remove objects from interior design images. Rather than using static, hardcoded parameters, the system leverages a dynamic routing engine that analyzes the 3D geometry and physical distance of the user's click to generate a custom execution context on the fly.

## Core Components

### 1. Dynamic Context Router (`VarianceBasedRoutingStrategy`)

Acting as the analytical brain of the system, this module evaluates the Depth Map Variance and Depth Ratio (distance from the camera) around the user's click to generate a targeted execution dictionary:

- **Input Routing**: Chooses the raw RGB image for flat surfaces (walls, TVs, windows) to utilize color contrast, or the Depth Map for 3D objects (sofas, poufs) to bypass texture confusion.
- **Dynamic Mask Expansion**: Calculates the required mask dilation based on the object's distance. Very close objects receive massive expansion (e.g., up to 100px) to completely swallow cast shadows, while distant objects receive minimal expansion (e.g., 10-15px) to preserve surrounding wall structures.
- **Diffusion Strength Modulation**: Adjusts the denoising strength of the Stable Diffusion model. Flat walls receive gentle blending (`0.50`) to prevent hallucinations, while 3D objects removed from carpets receive aggressive redrawing (`0.85`) to overwrite structural artifacts.
- **Mask Specificity (`use_broad_mask`)**: Instructs the segmentation engine whether to use a tight boundary (for flat objects) or a broad volume (for 3D furniture).

### 2. Segmentation Engine (`SamFacadeSingleton`)

Utilizes Meta's Segment Anything Model (SAM) loaded as a memory-efficient Singleton.

- Listens to the Dynamic Router to select either `masks[0]` (tight) or `masks[1]` (broad).
- Implements **Morphological Dilation** using OpenCV circular kernels to smoothly expand the chosen mask and encapsulate shadows based on the router's `expand_pixels` directive.

### 3. Hybrid Inpainting Engine (`HybridInpainter`)

A two-phase generative pipeline that balances structural integrity with photorealistic textures:

- **Phase 1 (Structural - LaMa)**: Uses the `LamaInpainter` to completely erase the masked object and its shadows, building a structural background approximation.
- **Phase 2 (Textural - Stable Diffusion)**: Uses the `StableDiffusionInpainter` to refine the LaMa output. It applies the dynamically calculated `sd_strength` to weave high-frequency details (wood grain, carpet fibers, realistic lighting) back into the erased area.
- **High-Res Compositing**: The generative outputs are mathematically blended back into the original high-resolution image using alpha compositing, ensuring the rest of the room loses exactly 0% of its original quality.
