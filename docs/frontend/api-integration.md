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

Response is `InpaintMaskResponse`, which extends `ClickResultResponse` and adds `object_id` and `object_uuid`:

```ts
{
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
  object_id: number;
  object_uuid: string;
}
```

`MainPage` turns base64 strings into `data:image/png;base64,...` URLs and drops them into existing result rendering.

## Sessions

`getSessions()` fetches `GET /images/sessions` and returns `SessionInfo[]`. Each entry has `uid` and `name` (nullable). Previously returned bare `string[]`; updated after session naming was added.

`setSessionName(uid, name)` posts `{name}` to `POST /images/{uid}/name` and returns the updated `SessionInfo`. Backend enforces uniqueness — on collision the backend returns 409 and `handleJsonResponse` throws with the body text, which `MainPage` routes to the error modal.

### Dashboard preview thumbnails

`sessionPreviewUrl(uid, lastChanged)` builds a `GET /images/{uid}/preview` URL with `lastChanged` as a `?t=` cache-buster; `SessionCard` renders it directly as an `<img src>` and falls back to a placeholder on `onError` (404 when no preview exists yet).

`saveSessionPreview(uid, imageB64)` posts `{ image_b64 }` to `POST /images/{uid}/preview`, best-effort (caller swallows failures). `PREVIEW_API_READY` in `api/images.ts` gates both — currently `true`.

`WorkspaceScreen` composites the thumbnail client-side (`utils/preview.ts::composeSessionPreview` — background plus every visible cutout at its current offset, drawn onto an offscreen canvas, downscaled to 640px, JPEG q0.82) and calls `saveSessionPreview` debounced ~1.5s after any mutation settles: inpaint, novel-view result, rename, duplicate, drag-end, delete, and hide/show toggles. The backend also writes an initial thumbnail at upload time (a downscaled copy of the original), so a session never shows an empty placeholder once uploaded.

## Objects

`getSessionObjects(uid)` fetches `GET /images/${uid}/objects` and returns `ObjectListResponse`. Used by `MainPage` on session restore to populate the full `objects[]` array. Each `ObjectInfo` may include `uuid`, `name`, and `average_depth` when metadata was persisted at inpaint time.

`getObjectByUuid(objectUuid)` fetches `GET /images/objects/${objectUuid}` and returns `ObjectMetadataResponse`.

`setObjectName(objectUuid, name)` sends `PATCH /images/objects/${objectUuid}` with `{ name }`.

`POST /images/objects/{uuid}/rescale-by-depth` exists on the backend but has no frontend wrapper or UI wiring yet.

## 3D

`generate3DModel(uid, objectId)` posts to `POST /3d/test-3d` with body `{ uid, object_id: objectId }`. Returns raw GLB `ArrayBuffer`.

`fetchCached3DModel(uid, objectId)` fetches `GET /3d/${uid}/${objectId}` and returns `null` on 404 (model not yet generated for that object).

## Session management

`getUidCacheStatus(uid)` fetches `GET /images/${uid}/cache` for session restore.

`deleteSession(uid)` calls `DELETE /images/${uid}` (no body). Throws on non-2xx.

## Legacy

`clickImage(payload)` remains for `POST /images/click`, but normal UI flow uses `segmentImage(...)` followed by `inpaintMask(...)`.
