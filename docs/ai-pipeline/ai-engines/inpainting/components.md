# Inpainting components

Source: [`TestModules/src/ai_engines/inpainting/`](../../../../TestModules/src/ai_engines/inpainting/).

- **`ImageInpaintingFacade`** — `inpaint(image, mask, **kwargs)` entry used by core.
- **`ImageInpaintingStrategy`** — ABC.
- **`LamaInpaintingStrategy`** — Structural inpainting via `simple_lama_inpainting`.
- **`StableDiffusionInpaintingStrategy`** — Refinement pass via diffusers inpainting pipeline. Runs SD on a **native-resolution crop around the mask** (`mask_crop_window` + `crop_with_window` from `inpainting_verification/crop.py`) rather than squashing the full frame to 512×512. Generation dims are snapped to the VAE's /8 grid (`_snap_to_multiple_of_8`). Only mask pixels are written back to the full-frame output; all surrounding pixels are byte-identical to the input. Constants: `SD_CROP_PAD_RATIO=0.35`, `SD_MIN_CROP_PX=512`, `SD_MAX_GEN_SIDE=1024` (OOM guard).
- **`HybridInpaintingStrategy`** — Default: LaMa first; optional SD when strength above threshold.
