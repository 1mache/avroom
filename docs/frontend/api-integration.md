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

Response is `InpaintMaskResponse`, which extends `ClickResultResponse` and adds `object_id`:

```ts
{
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
  object_id: number;   // zero-based id assigned to this object within the session
}
```

`MainPage` turns base64 strings into `data:image/png;base64,...` URLs and drops them into existing result rendering.

## Sessions

`getSessions()` fetches `GET /images/sessions` and returns `SessionInfo[]`. Each entry has `uid` and `name` (nullable). Previously returned bare `string[]`; updated after session naming was added.

`setSessionName(uid, name)` posts `{name}` to `POST /images/{uid}/name` and returns the updated `SessionInfo`. Backend enforces uniqueness — on collision the backend returns 409 and `handleJsonResponse` throws with the body text, which `MainPage` routes to the error modal.

## Objects

`getSessionObjects(uid)` fetches `GET /images/${uid}/objects` and returns `ObjectListResponse`. Used by `MainPage` on session restore to populate the full `objects[]` array.

## 3D

`generate3DModel(uid, objectId)` posts to `POST /3d/test-3d` with body `{ uid, object_id: objectId }`. Returns raw GLB `ArrayBuffer`.

`fetchCached3DModel(uid, objectId)` fetches `GET /3d/${uid}/${objectId}` and returns `null` on 404 (model not yet generated for that object).

## Session management

`getUidCacheStatus(uid)` fetches `GET /images/${uid}/cache` for session restore.

`deleteSession(uid)` calls `DELETE /images/${uid}` (no body). Throws on non-2xx.

## Legacy

`clickImage(payload)` remains for `POST /images/click`, but normal UI flow uses `segmentImage(...)` followed by `inpaintMask(...)`.
