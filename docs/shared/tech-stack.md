# Tech Stack

## Language & Runtime

- **Python 3.x** — entire backend and ML pipeline
- **Node.js / npm** — frontend toolchain only (Vite build)

## Core Python Libraries

| Library | Role |
|---|---|
| `opencv-python` (`cv2`) | Image loading, resizing, morphological operations, color-space conversions |
| `numpy` | Array math, mask arithmetic, depth blending |
| `Pillow` (PIL) | Image I/O for HuggingFace pipelines and LaMa; PIL ↔ numpy conversions |
| `torch` | Tensor backend for SAM and Stable Diffusion; CUDA detection |
| `transformers` | HuggingFace `pipeline()` wrapper used by `ImageDepthMapper` |
| `diffusers` | `StableDiffusionInpaintPipeline` used by `StableDiffusionInpainter` |
| `segment_anything` | Meta's SAM model registry and `SamPredictor` |
| `simple_lama_inpainting` | Convenience wrapper for the LaMa model |

## AI Models

### Depth Estimation

| Model | HuggingFace ID | Strength |
|---|---|---|
| Depth-Anything V2 Small | `depth-anything/Depth-Anything-V2-Small-hf` | Near-field / foreground objects |
| Depth-Anything (LiheYoung) | `LiheYoung/depth-anything-small-hf` | Far-field / background walls |

Both models are blended via alpha compositing — see [`optimized-depth-facade.md`](../pipeline/ai-engines/depth/optimized-depth-facade.md).

### Segmentation

| Model | Checkpoint | Notes |
|---|---|---|
| SAM ViT-B | `sam_vit_b_01ec64.pth` | Loaded from `TestModules/checkpoints/`. Auto-downloaded if absent. |

SAM is fed the **depth map**, not the RGB image, to avoid texture-based over-segmentation — see [`sam-facade.md`](../pipeline/ai-engines/segmentation/sam-facade.md).

### Inpainting

| Model | Source | Role |
|---|---|---|
| LaMa | `simple_lama_inpainting.SimpleLama` | Structural fill; run first |
| Stable Diffusion Inpainting | `runwayml/stable-diffusion-inpainting` | Texture refinement; run second if `strength > 0.2` |

## API Framework

- **FastAPI** — async HTTP server, Pydantic validation, auto-generated OpenAPI docs
- **Uvicorn** — ASGI server (`fastapi dev main.py` in development)

## Frontend

| Tool | Role |
|---|---|
| Vite | Build tool and dev server |
| React 18 | UI component framework |
| TypeScript | Type safety across the frontend |

## Hardware

- CUDA GPU (optional but recommended) — used by SAM, Stable Diffusion, and depth models when available
- Falls back gracefully to CPU; `float32` is used on CPU, `float16` on CUDA
