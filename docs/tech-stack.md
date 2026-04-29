# Tech Stack

Concrete versions of every meaningful dependency. Numbers come from the lockfiles in the repo; if they don't match, the lockfile wins.

## Languages and runtimes

- **Python**: `>=3.11` (declared in [`TestModules/pyproject.toml`](../TestModules/pyproject.toml) line 9).
- **TypeScript**: `~5.9.3` (dev dep in [`react-front/package.json`](../react-front/package.json) line 12).
- **Node.js**: not pinned in the repo; whatever Vite 5 supports.

## Frontend ([react-front/](../react-front/))

From [`react-front/package.json`](../react-front/package.json):

| Package | Version | Role |
|---|---|---|
| `react` | `^19.2.4` | UI library |
| `react-dom` | `^19.2.4` | DOM renderer |
| `@types/react` | `^19.2.14` | Types |
| `@types/react-dom` | `^19.2.3` | Types |
| `vite` | `^5.4.0` | Dev server + bundler |
| `typescript` | `~5.9.3` | Type checker |

There is **no** state-management library, **no** router, **no** HTTP client (uses native `fetch`), and **no** styling framework — just one `style.css` file.

## Backend + AI pipeline (Python)

The root [`requirements.txt`](../requirements.txt) is the canonical source. Highlights, grouped by purpose:

### Web framework

| Package | Version |
|---|---|
| `fastapi` | `0.135.1` |
| `fastapi-cli` | `0.0.24` |
| `starlette` | `0.52.1` |
| `uvicorn` | `0.41.0` |
| `pydantic` | `2.12.5` |
| `pydantic-settings` | `2.13.1` |
| `python-multipart` | `0.0.22` |

### Computer vision / image I/O

| Package | Version |
|---|---|
| `opencv-python` | `4.11.0.86` |
| `Pillow` | `9.5.0` |
| `numpy` | `1.26.4` |

### Deep learning runtime

| Package | Version |
|---|---|
| `torch` | `2.10.0` |
| `torchvision` | `0.25.0` |
| `torchaudio` | `2.10.0` |
| `transformers` | `5.3.0` |
| `diffusers` | `0.37.0` |
| `accelerate` | `1.13.0` |
| `huggingface_hub` | `1.6.0` |
| `safetensors` | `0.7.0` |
| `tokenizers` | `0.22.2` |

### AI models / wrappers

| Package | Version | Used by |
|---|---|---|
| `segment-anything` | `1.0` | [`SamFacadeSingleton`](../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) |
| `simple-lama-inpainting` | `0.1.2` | [`LamaInpainter`](../TestModules/src/ai_engines/inpainting/LamaInpainter.py) |

### Local package

```1:1:requirements.txt
-e ./TestModules
```

Installs `avroom_object_removal` editable (sources in `TestModules/src/`).

The same `requirements.txt` also installs the Trellis wrapper package editable:

```80:81:requirements.txt
gradio_client>=1.4
-e ./TrellisModule
```

Installs `avroom_trellis` editable (sources in `TrellisModule/src/`). See [trellis-module.md](trellis-module.md).

## AI models (downloaded at runtime)

These are **not** Python packages — they're pulled from Hugging Face / Facebook AI on first use:

| Model | Used as | Source |
|---|---|---|
| `depth-anything/Depth-Anything-V2-Small-hf` | Near-field depth | [`OptimizedDepthFacade`](../TestModules/src/ai_engines/depth/OptimizedDepthFacade.py) line 17 |
| `LiheYoung/depth-anything-small-hf` | Far-field depth + default | [`OptimizedDepthFacade`](../TestModules/src/ai_engines/depth/OptimizedDepthFacade.py) line 23, [`ImageDepthMapper`](../TestModules/src/ai_engines/depth/ImageDepthMapper.py) line 30 |
| `sam_vit_b_01ec64.pth` (SAM ViT-B) | Segmentation | [`SamFacadeSingleton`](../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) line 16, default URL `https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth` |
| `runwayml/stable-diffusion-inpainting` | Texture refinement | [`StableDiffusionInpainter`](../TestModules/src/ai_engines/inpainting/StableDiffusionInpainter.py) line 16 |
| LaMa weights (bundled with `simple_lama_inpainting`) | Structural inpainting | [`LamaInpainter`](../TestModules/src/ai_engines/inpainting/LamaInpainter.py) line 20 |

SAM checkpoint resolution order is `SAM_CHECKPOINT_PATH` env var → `TestModules/checkpoints/sam_vit_b_01ec64.pth` → auto-download (unless `SAM_AUTO_DOWNLOAD=0`).

## Hardware

- The pipeline auto-detects CUDA. SD and SAM call `torch.cuda.is_available()` and switch between `float16`/`float32` accordingly ([`StableDiffusionInpainter.py`](../TestModules/src/ai_engines/inpainting/StableDiffusionInpainter.py) lines 17–31, [`SamFacadeSingleton.py`](../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) line 72).
- CPU inference works but is slow.

## Build / dev commands

| Tier | Command | Where |
|---|---|---|
| Frontend dev | `npm run dev` | `react-front/` |
| Frontend build | `npm run build` (= `tsc && vite build`) | `react-front/` |
| Frontend preview | `npm run preview` | `react-front/` |
| Backend run | `uvicorn main:app --reload` | `fastApi-app/` |
| Pipeline install | `pip install -e ./TestModules` | repo root |
