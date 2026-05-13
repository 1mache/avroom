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
| `three` | `^0.184.0` | 3D viewer (GLB in browser) |
| `@types/three` | `^0.184.0` | Types |
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
| `segment-anything` | `1.0` | [`SamSegmentationStrategy`](../TestModules/src/ai_engines/segmentation/strategies/sam_segmentation_strategy.py) |
| `simple-lama-inpainting` | `0.1.2` | [`LamaInpaintingStrategy`](../TestModules/src/ai_engines/inpainting/strategies/lama_inpainting_strategy.py) |
| `gradio_client` | `>=1.4` | [`TrellisReconstructionStrategy`](../TestModules/src/ai_engines/reconstruction_3d/strategies/trellis_reconstruction_strategy.py) only (optional 3D backend) |
| `imageio[ffmpeg]` | `>=2.31.0` | Vendored OpenLRM imports (`_backends/openlrm_v10/lrm/`) |
| `PyMCubes` | `>=0.1.4` | [`OpenLrmReconstructionStrategy`](../TestModules/src/ai_engines/reconstruction_3d/strategies/openlrm_reconstruction_strategy.py) (marching cubes) |
| `trimesh` | `>=4.0.0` | [`OpenLrmReconstructionStrategy`](../TestModules/src/ai_engines/reconstruction_3d/strategies/openlrm_reconstruction_strategy.py) (mesh I/O + GLB) |

### Local package

```1:1:requirements.txt
-e ./TestModules
```

Installs `avroom_object_removal` editable (sources in `TestModules/src/`). The package owns the depth, segmentation, inpainting, and 3D reconstruction domains; there is no longer a separate Trellis package — see [ai-pipeline/ai-engines/reconstruction-3d/README.md](ai-pipeline/ai-engines/reconstruction-3d/README.md).

## AI models (downloaded at runtime)

These are **not** Python packages — they're pulled from Hugging Face / Facebook AI on first use:

| Model | Used as | Source |
|---|---|---|
| `depth-anything/Depth-Anything-V2-Small-hf` | Near-field depth | [`NearFarBlendedDepthMappingStrategy.DEFAULT_NEAR_MODEL`](../TestModules/src/ai_engines/depth/strategies/near_far_blended_depth_mapping_strategy.py) line 30 |
| `LiheYoung/depth-anything-small-hf` | Far-field depth + default | [`NearFarBlendedDepthMappingStrategy.DEFAULT_FAR_MODEL`](../TestModules/src/ai_engines/depth/strategies/near_far_blended_depth_mapping_strategy.py) line 31, [`DepthAnythingMappingStrategy.DEFAULT_MODEL`](../TestModules/src/ai_engines/depth/strategies/depth_anything_mapping_strategy.py) line 40 |
| `sam_vit_b_01ec64.pth` (SAM ViT-B) | Segmentation | [`SamSegmentationStrategy`](../TestModules/src/ai_engines/segmentation/strategies/sam_segmentation_strategy.py) lines 19–20, default URL `https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth` |
| `runwayml/stable-diffusion-inpainting` | Texture refinement | [`StableDiffusionInpaintingStrategy`](../TestModules/src/ai_engines/inpainting/strategies/stable_diffusion_inpainting_strategy.py) line 16 |
| LaMa weights (bundled with `simple_lama_inpainting`) | Structural inpainting | [`LamaInpaintingStrategy._load_simple_lama`](../TestModules/src/ai_engines/inpainting/strategies/lama_inpainting_strategy.py) lines 16–25 |
| `stabilityai/TripoSR` (HF weights + config) | Default 3D reconstruction (not in `/images/*` HTTP path) | [`TriposrReconstructionStrategy`](../TestModules/src/ai_engines/reconstruction_3d/strategies/triposr_reconstruction_strategy.py) lines 94–116 |
| `zxhezexin/openlrm-small-obj-1.0` (HF weights + config) | Optional 3D reconstruction strategy | [reconstruction-3d/operations.md](ai-pipeline/ai-engines/reconstruction-3d/operations.md) — cache dirs and `OPENLRM_WEIGHT_CACHE` |
| `microsoft/TRELLIS.2` (HF Space, image-to-3D) | Optional 3D reconstruction when using Trellis strategy (not in HTTP path) | [`TrellisReconstructionStrategy.DEFAULT_SPACE_ID`](../TestModules/src/ai_engines/reconstruction_3d/strategies/trellis_reconstruction_strategy.py) line 35 |

SAM checkpoint resolution order is `SAM_CHECKPOINT_PATH` env var → `TestModules/checkpoints/sam_vit_b_01ec64.pth` → auto-download (unless `SAM_AUTO_DOWNLOAD=0`). Heavy model loads (depth pipeline, SAM predictor, LaMa, SD pipe) are each cached behind a module-level `functools.lru_cache(maxsize=1)`/`maxsize=4` factory so they're loaded exactly once per process. The OpenLRM inferrer is also lazy-loaded behind `functools.lru_cache(maxsize=1)` in [`openlrm_reconstruction_strategy.py`](../TestModules/src/ai_engines/reconstruction_3d/strategies/openlrm_reconstruction_strategy.py) lines 40–49.

## Hardware

- The pipeline auto-detects CUDA. SD and SAM call `torch.cuda.is_available()` and switch between `float16`/`float32` accordingly ([`stable_diffusion_inpainting_strategy.py`](../TestModules/src/ai_engines/inpainting/strategies/stable_diffusion_inpainting_strategy.py) lines 41, 77–84, [`sam_segmentation_strategy.py`](../TestModules/src/ai_engines/segmentation/strategies/sam_segmentation_strategy.py) lines 107–114).
- CPU inference works but is slow.

## Build / dev commands

| Tier | Command | Where |
|---|---|---|
| Frontend dev | `npm run dev` | `react-front/` |
| Frontend build | `npm run build` (= `tsc && vite build`) | `react-front/` |
| Frontend preview | `npm run preview` | `react-front/` |
| Backend run | `uvicorn main:app --reload` | `fastApi-app/` |
| Pipeline install | `pip install -e ./TestModules` | repo root |
