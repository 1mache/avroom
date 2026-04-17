# Frontend API Client

**File:** `src/api/images.ts`

## Base URL

```typescript
const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";
```

Set `VITE_API_BASE_URL` in a `.env` file to point at a different backend (e.g., staging):

```
VITE_API_BASE_URL=https://api.example.com
```

## Functions

### `uploadImage(file: File) → Promise<ImageUploadResponse>`

Sends the file as `multipart/form-data` to `POST /images/upload`.

```typescript
const formData = new FormData();
formData.append("file", file);
const response = await fetch(`${API_BASE_URL}/images/upload`, {
  method: "POST",
  body: formData,
});
```

Returns the parsed `ImageUploadResponse`. Throws with the raw response text if the status is not OK.

### `clickImage(payload: ClickRequest) → Promise<ClickResultResponse>`

Sends the click payload as JSON to `POST /images/click`.

```typescript
const response = await fetch(`${API_BASE_URL}/images/click`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});
```

Returns the parsed `ClickResultResponse`. Throws with the raw response text if the status is not OK.

## Error Handling

Both functions use the shared `handleJsonResponse<T>` helper:

```typescript
async function handleJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}
```

Errors are caught in `MainPage` and displayed in the `error` state.

## TypeScript Types (`src/types/api.ts`)

| Type | Maps to API Schema |
|---|---|
| `ImageUploadResponse` | `ImageUploadResponse` |
| `ClickRequest` | `ClickRequest` |
| `ClickResultResponse` | `ClickResultResponse` |

These types mirror the Pydantic schemas defined in `fastApi-app/schemas/image.py`. See [`docs/api/schemas.md`](../../api/schemas.md).
