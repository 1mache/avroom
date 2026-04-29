# Inpainting components

Source: [`TestModules/src/ai_engines/inpainting/`](../../../../TestModules/src/ai_engines/inpainting/).

- **`ImageInpaintingFacade`** — `inpaint(image, mask, **kwargs)` entry used by core.
- **`ImageInpaintingStrategy`** — ABC.
- **`LamaInpaintingStrategy`** — Structural inpainting via `simple_lama_inpainting`.
- **`StableDiffusionInpaintingStrategy`** — Refinement pass via diffusers inpainting pipeline.
- **`HybridInpaintingStrategy`** — Default: LaMa first; optional SD when strength above threshold.
