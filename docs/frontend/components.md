# Frontend Components

## `App` (`src/App.tsx`)

Top-level component. Renders `<MainPage />` only. No state or logic — exists as the React tree root.

---

## `MainPage` (`src/components/layout/MainPage.tsx`)

The primary page component. Owns all application state and orchestrates the upload/click/run lifecycle.

### State

| State | Type | Description |
|---|---|---|
| `uploadedFile` | `File \| null` | The selected local file before upload |
| `uploadedImageUrl` | `string \| null` | Object URL for local image preview (`URL.createObjectURL`) |
| `imageId` | `string \| null` | UUID returned by the upload endpoint |
| `clickPosition` | `{x,y} \| null` | Display-space click position (used to render the red dot) |
| `naturalClickPos` | `{x,y} \| null` | Natural-resolution click position (sent to the API) |
| `backgroundSrc` | `string \| null` | Data URL for the inpainted background result |
| `cutoutSrc` | `string \| null` | Data URL for the cutout result |
| `isUploading` | `bool` | True while `POST /images/upload` is in flight |
| `isProcessing` | `bool` | True while `POST /images/click` is in flight |
| `error` | `string \| null` | Error message displayed to the user |

### Handlers

**`handleFileSelected(file)`**
- Resets all derivative state (imageId, click positions, results, errors)
- Creates a new object URL; revokes the previous one to prevent memory leaks
- Updates `uploadedFile` and `uploadedImageUrl`

**`handleImageClick(displayPos, naturalPos)`**
- Stores both the display-space position (for dot rendering) and natural-resolution position (for API)

**`handleUpload()`**
- Guards: requires `uploadedFile`
- Calls `uploadImage(file)` → stores `image_id`
- Sets `isUploading` true/false around the call

**`handleRun()`**
- Guards: requires `imageId` and `naturalClickPos`
- Constructs `ClickRequest { image_id, x: naturalClickPos.x, y: naturalClickPos.y }`
- Calls `clickImage(payload)` → builds data URLs from `background_b64` / `cutout_b64`
- Sets `isProcessing` true/false around the call

### Layout

- **Upload section** (`top-frame-section`): `<UploadFrame>` spans the full width
- **Bottom section** (`bottom-frame-section`): `<ResultFrame title="Background">` | action column | `<ResultFrame title="Cutout">`
- Action column contains Upload button, Run button, and error text
- Buttons are disabled while `isBusy` (uploading or processing)

---

## `UploadFrame` (`src/components/widgets/UploadFrame.tsx`)

Handles image display and click coordinate capture.

### Props

| Prop | Type | Description |
|---|---|---|
| `imageSrc` | `string \| null` | Object URL of the uploaded image; `null` shows the placeholder |
| `clickPosition` | `{x,y} \| null` | Display-space position for the red dot overlay |
| `onFileSelected` | `(file: File) => void` | Called when a file is chosen via the hidden input |
| `onImageClick` | `(displayPos, naturalPos) => void` | Called with both coordinate systems on each click |
| `disabled` | `bool` | Prevents clicks while busy |

### Behavior

**No image loaded:** Clicking the placeholder triggers `inputRef.current.click()` to open the file picker.

**Image loaded:** Clicking the container captures the click event and calculates two coordinate sets:
1. **Display position** — relative to the container element's bounding box (for dot placement)
2. **Natural position** — scaled to the image's actual pixel dimensions:

```typescript
const naturalPos = {
  x: Math.round((clickXOnImg / imgRect.width)  * img.naturalWidth),
  y: Math.round((clickYOnImg / imgRect.height) * img.naturalHeight),
};
```

The natural position is what gets sent to the API. This ensures the coordinates are correct regardless of how the image is displayed (scaled down, padded, etc.).

**Red dot:** When `clickPosition` and `imageSrc` are both set, an absolutely-positioned `div.click-dot` is placed at `{ left: clickPosition.x, top: clickPosition.y }`.

---

## `ResultFrame` (`src/components/widgets/ResultFrame.tsx`)

A simple display widget. Shows a title and either a loading/empty placeholder or a `<img>` with the provided `src`.

### Props

| Prop | Type | Description |
|---|---|---|
| `title` | `string` | Label displayed above the image |
| `imageSrc` | `string \| null` | Data URL to display; `null` shows an empty frame |
