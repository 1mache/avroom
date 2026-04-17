# LamaInpainter

**File:** `TestModules/src/ai_engines/inpainting/LamaInpainter.py`

## Responsibility

`LamaInpainter` performs structural inpainting using the [LaMa (Large Mask Inpainting)](https://github.com/advimman/lama) model. It fills masked regions with plausible background texture, producing clean, structure-preserving results. It is always the first stage in `HybridInpainter`.

It implements `IInpainter` and is itself a singleton.

## Singleton Behavior

`LamaInpainter` uses `__new__` to ensure the `SimpleLama` model is loaded only once:

```python
lama = LamaInpainter()  # first call: loads model
lama2 = LamaInpainter() # same instance, no reload
```

## Pre-Fill Step (Ghost Prevention)

Before running LaMa, the mask region is filled with the **mean color of the mask boundary**:

```python
boundary = dilated_mask_bool & (~mask_bool)  # 1px ring outside mask
fill = image[boundary].mean(axis=0)          # average color of that ring
image[mask_bool] = fill
```

This prevents LaMa from being conditioned on the removed object's pixels. Without this step, LaMa can "see" the object color inside the mask and hallucinate a ghost of it in the output.

## Inpainting Flow

1. Fill mask area with boundary mean (ghost prevention)
2. Convert BGR → RGB (OpenCV to PIL/LaMa)
3. Ensure mask is uint8 0–255; convert to PIL grayscale `'L'`
4. Call `self.lama(image_pil, mask_pil)` → PIL result
5. Convert result RGB → BGR (back to OpenCV convention)
6. Return BGR `np.ndarray`

## Input / Output

| Parameter | Format |
|---|---|
| `image` | BGR `np.ndarray` (OpenCV) |
| `mask` | uint8 or bool `np.ndarray`; values > 127 / `True` = fill region |
| Return | BGR `np.ndarray` same dimensions as input |

## Mask Size Handling

If the mask and image differ in spatial dimensions (which can happen when SAM/depth produce slightly different outputs), the mask is resized with `cv2.INTER_NEAREST` before processing:

```python
if mask.shape[:2] != image.shape[:2]:
    mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
```
