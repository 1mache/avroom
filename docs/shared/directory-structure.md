# Directory Structure

## Repository Root (`avroom/`)

```
avroom/
├── avroom_context.md          # Legacy index — see docs/ for full documentation
├── requirements.txt           # Pinned Python dependencies for the entire project
├── .gitignore                 # Ignores venvs, checkpoints, test I/O, __pycache__
├── debug-16a8ad.log           # Runtime log (not committed in normal operation)
│
├── docs/                      # Internal documentation (this folder)
│
├── fastApi-app/               # FastAPI HTTP service
├── TestModules/               # CV/ML pipeline (Python)
└── react-front/               # Vite + React UI
```

## `fastApi-app/` — API Service

```
fastApi-app/
├── main.py                    # FastAPI app factory, CORS config, router mounting
├── settings.py                # IMAGE_STORAGE_DIR configuration
├── pyproject.toml             # FastAPI project metadata
├── .gitignore
├── .venv/                     # Python virtual environment (gitignored)
├── api/
│   ├── __init__.py
│   └── routes.py              # /images/upload and /images/click endpoints
├── core/
│   ├── __init__.py
│   └── image_processing.py    # segment_at_click(), process_click_on_image()
├── schemas/
│   ├── __init__.py
│   └── image.py               # Pydantic request/response models
└── images/                    # Runtime image storage (gitignored content)
    └── tmp/                   # Debug overlay images per click
```

## `TestModules/` — CV/ML Pipeline

```
TestModules/
├── src/
│   ├── core/
│   │   ├── objectRemover.py   # Main orchestrator: ObjectRemover class
│   │   └── interfaces.py      # Abstract interfaces for all components
│   ├── ai_engines/
│   │   ├── depth/
│   │   │   ├── ImageDepthMapper.py         # HuggingFace depth pipeline wrapper
│   │   │   └── OptimizedDepthFacade.py     # Near+Far depth blending
│   │   ├── segmentation/
│   │   │   ├── SamFacadeSingleton.py       # SAM model loader + predictor
│   │   │   └── SamImageAdapter.py          # depth → RGB adapter with caching
│   │   └── inpainting/
│   │       ├── LamaInpainter.py            # LaMa structural inpainting
│   │       ├── StableDiffusionInpainter.py # SD texture refinement
│   │       └── HybridInpainter.py          # LaMa → SD composite pipeline
│   ├── routing/
│   │   ├── boundary_variance_strategy.py   # ACTIVE: boundary ring depth variance
│   │   ├── gradient_variance_routing_strategy.py
│   │   ├── variance_based_routing_strategy.py
│   │   ├── center_of_mass_routing_strategy.py
│   │   └── topographic_routing_strategy.py
│   ├── utils/
│   │   ├── MaskRefiner.py                  # Morphological mask operations
│   │   ├── MaskOverlapRGBAComposer.py      # BGRA cutout composition
│   │   ├── DebugImageSaver.py              # Writes debug images to outputs/
│   │   └── imageAdapterFactory.py          # PIL → RGB numpy utility loader
│   └── GuiTestClicker.py                   # OpenCV GUI for local testing
├── tests/
│   ├── test_pipeline_runner.py
│   ├── depthModelTest.py
│   ├── samMasksTest.py
│   └── downloadTestModelWeights.py
├── checkpoints/               # GITIGNORED — SAM .pth weight files
├── inputs/                    # GITIGNORED — test source images
└── outputs/                   # GITIGNORED — debug and result images
```

## `react-front/` — Frontend

```
react-front/
├── index.html
├── package.json
├── package-lock.json
├── tsconfig.json
├── .gitignore
├── public/
│   ├── favicon.svg
│   └── icons.svg
└── src/
    ├── main.tsx               # React root mount
    ├── App.tsx                # Top-level component (renders MainPage)
    ├── style.css
    ├── counter.ts
    ├── api/
    │   └── images.ts          # uploadImage(), clickImage() fetch wrappers
    ├── types/
    │   └── api.ts             # TypeScript types for API payloads
    ├── components/
    │   ├── layout/
    │   │   └── MainPage.tsx   # Main application page
    │   └── widgets/
    │       ├── UploadFrame.tsx  # Image upload + click selection widget
    │       └── ResultFrame.tsx  # Display widget for background/cutout
    └── assets/
        ├── hero.png
        ├── typescript.svg
        └── vite.svg
```

## Gitignored Runtime Paths

These paths are expected to exist at runtime but are not committed:

| Path | Contents |
|---|---|
| `TestModules/checkpoints/` | SAM model weights (`sam_vit_b_01ec64.pth`) |
| `TestModules/inputs/` | Test images for manual pipeline runs |
| `TestModules/outputs/` | Debug intermediate images from `DebugImageSaver` |
| `fastApi-app/images/` | Uploaded images from API sessions |
| `fastApi-app/.venv/` | Python virtual environment |
| `**/__pycache__/` | Python bytecode cache |
| `**/*.pth` | Any additional PyTorch weight files |
