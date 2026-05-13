# User Flow

End-to-end interaction from the user's point of view, with the file:line references that drive each step.

## Sequence

```mermaid
sequenceDiagram
    actor User
    participant UF as UploadFrame
    participant MP as MainPage
    participant API as "api/images.ts"
    participant Backend as "FastAPI backend"
    participant RF as ResultFrame

    User->>UF: click empty placeholder
    UF->>UF: inputRef.current.click()
    User->>UF: pick file
    UF->>MP: onFileSelected(file)
    MP->>MP: URL.createObjectURL -> uploadedImageUrl
    Note over UF: shows preview

    User->>MP: click "Upload"
    MP->>API: uploadImage(file)
    API->>Backend: POST /images/upload (multipart)
    Backend-->>API: ImageUploadResponse
    API-->>MP: imageId

    User->>UF: click on image
    UF->>UF: compute display + natural coords
    UF->>MP: onImageClick(displayPos, naturalPos)
    Note over UF: red dot at displayPos

    User->>MP: click "Run"
    MP->>API: clickImage({image_id, x, y})
    API->>Backend: POST /images/click (json)
    Backend-->>API: ClickResultResponse
    API-->>MP: background_b64, cutout_b64, format
    MP->>MP: build data URLs
    MP-->>RF: imageSrc for Background
    MP-->>RF: imageSrc for Cutout
```

## Step references

| Step | Code |
|---|---|
| Hidden `<input type="file">` opens picker on placeholder click | [`UploadFrame.tsx`](../../react-front/src/components/widgets/UploadFrame.tsx) lines 30–41 |
| File picked → `onFileSelected` | [`UploadFrame.tsx`](../../react-front/src/components/widgets/UploadFrame.tsx) lines 22–28 |
| `MainPage.handleFileSelected` resets state, makes object URL | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 34–51 |
| `URL.createObjectURL` cleanup on unmount | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 26–32 |
| Upload button → `handleUpload` → `uploadImage` | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 58–77, [`api/images.ts`](../../react-front/src/api/images.ts) lines 15–25 |
| Click on image → display + natural coords | [`UploadFrame.tsx`](../../react-front/src/components/widgets/UploadFrame.tsx) lines 30–63 |
| Run button → `handleRun` → `clickImage` | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 79–111, [`api/images.ts`](../../react-front/src/api/images.ts) lines 27–37 |
| Build data URLs and set state | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 99–103 |
| Render results | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 135–161, [`ResultFrame.tsx`](../../react-front/src/components/widgets/ResultFrame.tsx) |

## Edge cases handled in the UI

- **Run pressed without an upload** — `handleRun` early-returns with `setError("No uploaded image to process yet.")` ([`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 80–83).
- **Run pressed without a click** — early-returns with `setError("Please click on the image to select a point of interest.")` ([`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 85–88).
- **Backend returns non-2xx** — `handleJsonResponse` throws with the response text; the catch block surfaces it via `setError`.
- **File replaced before re-uploading** — all derived state is cleared, including the previous `imageId`. The Run button stays disabled until a new upload completes.

## Session restore flow

A parallel path: the user picks a prior session from the `SessionPicker` sidebar instead of uploading a new file.

```mermaid
sequenceDiagram
    actor User
    participant SP as SessionPicker
    participant MP as MainPage
    participant API as "api/images.ts"
    participant Backend as "FastAPI backend"

    SP->>API: getSessions()
    API->>Backend: GET /images/sessions
    Backend-->>API: ["uid1","uid2",...]
    API-->>SP: string[]
    SP->>API: getUidCacheStatus(uid) x N (parallel)
    API->>Backend: GET /images/{uid}/cache
    Backend-->>API: UidCacheStatusResponse
    SP->>SP: render list with hasResults flags

    User->>SP: click session entry
    SP->>MP: onSessionSelect(uid)
    MP->>MP: setImageId, clear click state
    MP->>MP: uploadedImageUrl = /images/uid/original
    MP->>API: getUidCacheStatus(uid)
    API->>Backend: GET /images/{uid}/cache
    Backend-->>API: UidCacheStatusResponse
    MP->>MP: if has_background -> backgroundSrc = /images/uid/background
    MP->>MP: if has_cutout -> cutoutSrc = /images/uid/cutout
```

| Step | Code |
|---|---|
| `SessionPicker` mounts, fetches sessions | [`SessionPicker.tsx`](../../react-front/src/components/widgets/SessionPicker.tsx) lines 16–42 |
| Parallel cache status checks | [`SessionPicker.tsx`](../../react-front/src/components/widgets/SessionPicker.tsx) lines 23–31 |
| User clicks session → `handleSessionSelect` | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 65–84 |
| Conditional background/cutout restore | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 77–83 |

After session restore the user can click the image and run segmentation again — the existing `imageId` is already set so the Run button becomes available once a click is registered.

## What the UI deliberately does not do

- No drag-and-drop file pick (only the `<input>`).
- No zoom / pan / crop tools.
- No multi-click / multi-region selection — one click drives one segmentation.
- No history / undo of past results.
