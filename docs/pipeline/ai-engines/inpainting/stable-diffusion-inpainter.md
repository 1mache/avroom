# StableDiffusionInpainter

**File:** `TestModules/src/ai_engines/inpainting/StableDiffusionInpainter.py`

## Responsibility

`StableDiffusionInpainter` performs generative texture refinement on a pre-inpainted image using the Stable Diffusion inpainting pipeline. It is the second stage in `HybridInpainter` and only runs when the routing `strength` value is above 0.2.

It implements `IInpainter`.

## Model

- **HuggingFace ID:** `runwayml/stable-diffusion-inpainting`
- Loaded via `diffusers.StableDiffusionInpaintPipeline`
- Uses `torch.float16` on CUDA, `torch.float32` on CPU
- `pipe.enable_attention_slicing()` is called on CUDA to reduce VRAM usage

## Fixed Prompts

The prompts are hardcoded to encourage empty, seamless backgrounds:

```python
SD_prompt = "seamless plain flat background texture, photorealistic background, empty space"
SD_negative_prompt = "furniture, table, couch, chair, sofa, ottoman, pouf, stool, vase, plant, object, item, thing, decor, shadow, 3d, person, animal, clutter, artifact, pedestal, box, blurry, smeared, ghost"
```

The negative prompt aggressively suppresses any tendency to generate new objects in the removed space.

## Inference Parameters

| Parameter | Value | Notes |
|---|---|---|
| `num_inference_steps` | `30` | Quality vs speed trade-off |
| `guidance_scale` | `10.0` | High guidance = stronger prompt adherence |
| `strength` | dynamic (from router) | Controls how much of the image SD can repaint |

## Resolution Handling

SD runs at **512×512** regardless of the source image size:

1. Image and mask are resized to 512×512 before inference
2. Mask is binarized strictly (`> 127`) to keep hard edges
3. After inference, the result is resized back to the original resolution using `Image.LANCZOS`
4. Finally converted from RGB PIL back to BGR numpy for cv2 compatibility

## `strength` Parameter

`strength` is the key control passed from `ObjectRemover` via the router:

- `strength = 0.35` (default from `BoundaryVarianceRoutingStrategy`) — SD makes modest changes, preserving LaMa's structural result
- `strength ≤ 0.2` — SD step is **skipped entirely** by `HybridInpainter` (LaMa-only path)
- Higher values → SD can change more pixels, increasing quality but also risk of hallucination

## Input / Output

| Parameter | Format |
|---|---|
| `image` | BGR `np.ndarray` |
| `mask` | uint8 `np.ndarray`; values > 127 = fill region |
| `prompt` | `str \| None`; if `None`, the hardcoded `SD_prompt` is used |
| `strength` | `float`, default `0.35` |
| Return | BGR `np.ndarray` same spatial dimensions as input |
