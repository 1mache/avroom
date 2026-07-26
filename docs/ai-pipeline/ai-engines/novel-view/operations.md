# Novel view operations

## Default backend (Stable Zero123)

`NovelViewFacade` defaults to `StableZero123NovelViewStrategy` using Hugging Face model **`kxic/stable-zero123`**.

This is a community Diffusers conversion (~5 GB) of Stability's Stable Zero123 weights, published by the [zero123-hf](https://github.com/kxhit/zero123-hf) author. It includes `model_index.json` and all pipeline components required by Diffusers.

**Weight provenance:** converted from the official **`stabilityai/stable-zero123`** checkpoint. That official repo is **ckpt-only** (`stable_zero123.ckpt`, ~8.5 GB) and is intended for threestudio — it cannot be loaded via `DiffusionPipeline.from_pretrained` directly.

Load path (manual component assembly — required for diffusers 0.37 + kxic repos):

```python
from diffusers.utils import get_class_from_dynamic_module
from huggingface_hub import snapshot_download

# StableZero123NovelViewStrategy loads subfolder weights from snapshot_download(model_id)
# and builds Zero1to3StableDiffusionPipeline from the community pipeline_zero1to3 module.
# DiffusionPipeline.from_pretrained(model_id, custom_pipeline=...) fails because
# model_index.json references cc_projection/pipeline_zero1to3.py which is not in the repo.
```

### Model id override

Set `NOVEL_VIEW_MODEL_ID` to point at another Diffusers-formatted Zero123 repo (e.g. a locally converted checkpoint directory):

```bash
# PowerShell
$env:NOVEL_VIEW_MODEL_ID = "C:\path\to\converted-zero123"
```

Pinned stack: `diffusers==0.37.0`, `torch>=2.1`, `kornia>=0.7` (required by the community pipeline).

### Advanced: self-convert official ckpt

If you prefer weights directly from Stability's repo:

1. Download `stable_zero123.ckpt` from [stabilityai/stable-zero123](https://huggingface.co/stabilityai/stable-zero123).
2. Use diffusers [`convert_zero123_to_diffusers.py`](https://github.com/huggingface/diffusers/blob/main/scripts/convert_zero123_to_diffusers.py) with the YAML config from [threestudio](https://github.com/threestudio-project/threestudio/blob/main/load/zero123/sd-objaverse-finetune-c_concat-256.yaml).
3. Point `NOVEL_VIEW_MODEL_ID` at the converted output directory.

This path is not automated in AVRoom; use it only if `kxic/stable-zero123` is unavailable.

## License

**Stability AI Non-Commercial Research Community License** applies to Stable Zero123 weights (whether loaded via `kxic/stable-zero123` or the official ckpt).

- OK for research / non-commercial MVP and internal experimentation.
- **Do not ship commercially** on this checkpoint without legal clearance or switching to an alternate model (e.g. Zero123++, Free3D, MetaView, or `stable-zero123-c` with active Stability membership).

Document any product-stage license decision before enabling in production.

## Hugging Face authentication

Set `HF_TOKEN` in `fastApi-app/.env` (loaded by `main.py` via `load_dotenv()`) for faster HF Hub downloads. The default `kxic/stable-zero123` repo is public and does not require auth.

## VRAM and GPU policy

- Stable Zero123 consumes VRAM similar to SD 1.5 (~6–8 GB for inference).
- The pipeline is lazy-loaded once per process via `@functools.lru_cache`.
- **CUDA strongly recommended.** CPU inference works but is very slow.
- First run downloads ~5 GB of weights from Hugging Face.
- If TripoSR/Hunyuan and Zero123 cannot coexist in VRAM, run them sequentially or document an exclusive-GPU unload policy.

## Inference defaults

| Parameter | Default | Notes |
|-----------|---------|-------|
| `guidance_scale` | `3.0` | Do not use ~7.5; pose over-amplifies |
| `num_inference_steps` | `50` | Wrapper default |
| `model_size` | `256` | Working resolution for Zero123-class models |
| `seed` | `0` | Passed to `torch.Generator` |

## Smoke test

From repo root (requires deps; CUDA recommended):

```bash
python TestModules/tests/test_novel_view_stable_zero123.py [path/to/cutout.png]
```

First run downloads `kxic/stable-zero123` (~5 GB). Debug outputs:

- `TestModules/outputs/novel_view_rotation_debug/preprocessing/` — stages 00–05 per azimuth
- `TestModules/outputs/novel_view_rotation_debug/final_results/` — generated novel views

## Pose direction constants (Python)

```python
from avroom_object_removal.ai_engines.novel_view import (
    BACK,
    FRONT,
    HIGH_TILT,
    LOW_TILT,
    QUARTER,
    SIDE,
    THREE_QUARTER,
    ZOOM_STEP,
    AzimuthDirection,
    ElevationDirection,
    NovelViewRotationAdapter,
    ZoomDirection,
)

# Counter-clockwise quarter turn
az = NovelViewRotationAdapter.to_signed_azimuth(QUARTER, AzimuthDirection.C_CLOCKWISE)
# -> -45.0
```

## API smoke test

After segment → inpaint has produced a cutout.

**Signed azimuth (backward compatible):**

```bash
curl -X POST http://127.0.0.1:8000/images/novel-view \
  -H "Content-Type: application/json" \
  -d '{"uid":"<session-uuid>","object_id":0,"elevation_deg":0,"azimuth_deg":45}'
```

**Readable directions (unsigned magnitudes):**

```bash
# 90° clockwise (side view), slight upward tilt, zoom in
curl -X POST http://127.0.0.1:8000/images/novel-view \
  -H "Content-Type: application/json" \
  -d '{
    "uid":"<session-uuid>",
    "object_id":0,
    "elevation_deg":0,
    "azimuth_deg":90,
    "azimuth_direction":"CLOCKWISE",
    "relative_elevation_deg":15,
    "elevation_direction":"UP",
    "radius":0.5,
    "zoom_direction":"ZOOM_IN"
  }'

# Back view via named constant magnitude
curl -X POST http://127.0.0.1:8000/images/novel-view \
  -H "Content-Type: application/json" \
  -d '{
    "uid":"<session-uuid>",
    "object_id":0,
    "elevation_deg":0,
    "azimuth_deg":180,
    "azimuth_direction":"C_CLOCKWISE"
  }'
```

Responses echo optional direction fields and return the resolved signed pose values.

## Disk cache

Successful responses write `{uid}_{object_id}_novel_az{azimuth}_el{rel_el}.png` under the image storage directory. The JSON contract is unchanged; cache is for debugging and repeat requests.

## Errors

- **`StableZero123NovelViewError`** — inference or pipeline failure inside TestModules. Load failures hint that `stabilityai/stable-zero123` is ckpt-only.
- HTTP **404** — cutout missing (run inpaint first).
- HTTP **422** — invalid pose direction combination (e.g. negative magnitude with a direction set).
- HTTP **500** — model load or inference failure (`logger.exception` before raise).
