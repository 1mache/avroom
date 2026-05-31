# API Integration

All backend traffic goes through [`react-front/src/api/images.ts`](../../react-front/src/api/images.ts). It uses native `fetch`.

## Base URL

`API_BASE_URL` reads `VITE_API_BASE_URL` or falls back to `http://127.0.0.1:8000`.

## Helpers

`handleJsonResponse<T>(...)` throws an `Error` with backend response text on non-2xx responses. `MainPage` shows that message in the error modal.

## Upload

`uploadImage(file)` posts multipart form data to `POST /images/upload` and returns `ImageUploadResponse`.

## Segmentation

`segmentImage(payload)` posts JSON to `POST /images/segment`.

Payload:

```ts
{ image_id: string; x: number; y: number; options?: ClickRequestOptions }
```

Response contains `masks[]`; each mask has:

- `mask_id` for later inpainting.
- `cutout_b64` preview rendered in modal.
- `format`, currently `png`.
- `cutout_bounds` for future final cutout drag behavior.

## Inpainting

`inpaintMask({ image_id, mask_id })` posts JSON to `POST /images/inpaint`.

Response mirrors legacy final result:

```ts
{
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
}
```

`MainPage` turns base64 strings into `data:image/png;base64,...` URLs and drops them into existing result rendering.

## 3D

`generate3DModel(uid)` still posts to `POST /objects/test-3d`. Backend expects final `{uid}_cutout.png`, now written by `/images/inpaint`.

`fetchCached3DModel(uid)` reads `GET /objects/{uid}` and returns `null` on 404.

## Legacy

`clickImage(payload)` remains for `POST /images/click`, but normal UI flow uses `segmentImage(...)` followed by `inpaintMask(...)`.
