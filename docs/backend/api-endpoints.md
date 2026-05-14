# API Endpoints

Image routes live in [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py). Object routes live in [`fastApi-app/api/objects.py`](../../fastApi-app/api/objects.py).

| Method | Path | Request | Response |
|---|---|---|---|
| `GET` | `/images/sessions` | none | `list[str]` |
| `POST` | `/images/upload` | multipart file | `ImageUploadResponse` |
| `POST` | `/images/click` | `ClickRequest` | `ClickResultResponse` |
| `GET` | `/images/{uid}/cache` | path `uid` | `UidCacheStatusResponse` |
| `GET` | `/images/{uid}/background` | path `uid` | PNG file |
| `GET` | `/images/{uid}/cutout` | path `uid` | PNG file |
| `GET` | `/images/{uid}/original` | path `uid` | original image file |
| `POST` | `/objects/test-3d` | `{"uid":"..."}` | GLB bytes |
| `GET` | `/objects/{uid}` | path `uid` | GLB file |

## `POST /images/click`

This endpoint gained one important piece of metadata: `cutout_bounds`.

### Behavior

1. Run segmentation/inpainting pipeline through `process_click_on_image(...)`.
2. Persist `{uid}_background.png` and `{uid}_cutout.png`.
3. Base64-encode both images for frontend.
4. Decode the cutout PNG again and inspect its alpha channel.
5. Build a tight visible-object bounding box from non-zero alpha pixels.
6. Return that box as `cutout_bounds` inside `ClickResultResponse`.

### Why extra decode pass exists

Segmentation already returns a full-size PNG aligned to original image. That PNG usually contains a lot of transparent padding around the real object.

Frontend drag clamp must answer:

- where does visible object start?
- where does it end?

Base64 alone is not enough. Returning `cutout_bounds` lets frontend clamp by actual visible object instead of full-image extent.

### Response shape

```json
{
  "image_id": "uuid",
  "background_b64": "...",
  "cutout_b64": "...",
  "format": "png",
  "cutout_bounds": {
    "left": 214,
    "top": 133,
    "right": 602,
    "bottom": 701,
    "natural_width": 1280,
    "natural_height": 960
  }
}
```

## `GET /images/{uid}/cache`

This endpoint also changed.

Old role:

- only answer whether background/cutout/3D artifacts exist

New role:

- answer existence flags
- also derive `cutout_bounds` from cached cutout PNG when present

### Why cache endpoint now returns geometry

Session restore path already uses `/cache` before rendering cached result assets. Adding `cutout_bounds` here means old sessions can drag immediately without forcing a new click/segmentation request.

### Cost model

- Reads cached cutout PNG from disk
- Decodes PNG with OpenCV
- Computes bounding rectangle from alpha channel

This work happens on demand and only when cached cutout exists.

## Bounds extraction helper

[`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) defines `_extract_cutout_bounds_from_png_bytes(...)`.

Behavior:

1. Decode image bytes with `cv2.imdecode(..., IMREAD_UNCHANGED)` so alpha channel survives.
2. If decode fails, return `None`.
3. If image has no alpha channel, fall back to full-image bounds.
4. Use `cv2.findNonZero(alpha)` to locate visible pixels.
5. If alpha is entirely empty, also fall back to full-image bounds.
6. Use `cv2.boundingRect(...)` to return tight rectangle.

Fallback-to-full-image rule is deliberate. It keeps API predictable even if cutout metadata is imperfect.

## `POST /images/upload`, asset file endpoints, and object endpoints

No semantic changes in these handlers. They still behave as before. Main difference is that frontend now depends on `/images/click` and `/images/{uid}/cache` returning the extra geometry field described above.
