# State and Types

The frontend has no global store. All state lives in `MainPage` via `useState`, plus the local `useRef`s inside `UploadFrame`.

## `MainPage` state

From [`react-front/src/components/layout/MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 14–24:

| Variable | Type | Set by | Used for |
|---|---|---|---|
| `uploadedFile` | `File \| null` | `handleFileSelected` | Source for `URL.createObjectURL` and the multipart upload. |
| `uploadedImageUrl` | `string \| null` | `handleFileSelected` | `<img src>` for live preview. Revoked on replacement / unmount. |
| `imageId` | `string \| null` | response of `uploadImage` | Sent on every click request. |
| `clickPosition` | `{ x; y } \| null` | `handleImageClick` (display coords) | Position of the red dot overlay. |
| `naturalClickPos` | `{ x; y } \| null` | `handleImageClick` (natural coords) | Sent in `ClickRequest`. |
| `backgroundSrc` | `string \| null` | response of `clickImage` | Data URL for the Background `ResultFrame`. |
| `cutoutSrc` | `string \| null` | response of `clickImage` | Data URL for the Cutout `ResultFrame`. |
| `isUploading` | `boolean` | `handleUpload` | Disables Upload button. |
| `isProcessing` | `boolean` | `handleRun` | Disables Run button. |
| `error` | `string \| null` | both async handlers | Shown under the action buttons. |

## State invariants

- Picking a new file resets `imageId`, `clickPosition`, `naturalClickPos`, `backgroundSrc`, `cutoutSrc`, and `error` ([`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 34–51). The user must re-upload after each new pick.
- The Run button is disabled until both `imageId` (server has the file) and `clickPosition` (the user has actually clicked) exist.
- `useEffect` cleanup revokes the latest object URL on unmount ([`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 26–32).

## `UploadFrame` refs

[`react-front/src/components/widgets/UploadFrame.tsx`](../../react-front/src/components/widgets/UploadFrame.tsx):

- `inputRef: HTMLInputElement` — the hidden file picker, `.click()`'d when the empty placeholder is pressed.
- `imageRef: HTMLImageElement` — used for `naturalWidth`/`naturalHeight` to scale clicks (see [components.md](components.md)).

## TypeScript types

All API types live in [`react-front/src/types/api.ts`](../../react-front/src/types/api.ts). They are the TypeScript mirror of the Pydantic models in [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py).

```1:24:react-front/src/types/api.ts
export interface ImageUploadResponse {
  image_id: string;
  original_filename?: string | null;
  stored_path?: string | null;
}

export interface ClickRequestOptions {
  output_format?: string;
  grayscale?: boolean;
}

export interface ClickRequest {
  image_id: string;
  x: number;
  y: number;
  options?: ClickRequestOptions;
}

export interface ClickResultResponse {
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
}
```

There is no codegen — when you change the Pydantic models in the backend, manually update this file too. The cross-references are documented in [backend/schemas.md](../backend/schemas.md).

## Local component types

`MainPage` declares a private `ClickPosition` interface ([`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 9–12) used purely as a tuple of `(x, y)` numbers in display or natural space. It is intentionally not exported — `UploadFrame` uses the same shape inline.
