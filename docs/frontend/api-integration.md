# API Integration

All backend traffic goes through [`react-front/src/api/images.ts`](../../react-front/src/api/images.ts). It uses the native `fetch` — there is no axios.

## Base URL

```3:4:react-front/src/api/images.ts
const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";
```

- Override with the Vite env var `VITE_API_BASE_URL`.
- Default points at the local FastAPI dev server.

There is no `.env*` checked into `react-front/`. If you want a different backend in dev, create `react-front/.env.local` with:

```
VITE_API_BASE_URL=http://my.host:8000
```

Vite injects this at build time; runtime changes require a rebuild/restart.

## Helpers

```6:13:react-front/src/api/images.ts
async function handleJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}
```

A thin wrapper that throws an `Error` whose message is either the response body text or a generic `Request failed with status NNN`. `MainPage` catches this and shows it under the action buttons.

## `uploadImage`

```15:25:react-front/src/api/images.ts
export async function uploadImage(file: File): Promise<ImageUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/images/upload`, {
    method: "POST",
    body: formData,
  });

  return handleJsonResponse<ImageUploadResponse>(response);
}
```

- The form field name `"file"` must match `UploadFile = File(...)` in [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) line 26.
- Browser sets the `multipart/form-data` boundary automatically — don't add an explicit `Content-Type` header.

## `clickImage`

```27:37:react-front/src/api/images.ts
export async function clickImage(payload: ClickRequest): Promise<ClickResultResponse> {
  const response = await fetch(`${API_BASE_URL}/images/click`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<ClickResultResponse>(response);
}
```

- JSON payload typed as [`ClickRequest`](../backend/schemas.md#clickrequest).
- The TS types in [`react-front/src/types/api.ts`](../../react-front/src/types/api.ts) mirror the backend Pydantic models — see [state-and-types.md](state-and-types.md).

## Auth, retries, timeouts

There are none. Each call is fire-once. If you add auth or retry behavior, wrap it inside `handleJsonResponse` rather than at every call site.

## Response handling in `MainPage`

```99:103:react-front/src/components/layout/MainPage.tsx
      const result = await clickImage(payload);
      const base64Prefix = `data:image/${result.format};base64,`;
      setBackgroundSrc(`${base64Prefix}${result.background_b64}`);
      setCutoutSrc(`${base64Prefix}${result.cutout_b64}`);
```

The base64 strings are turned into `data:image/png;base64,...` URLs and dropped straight into `<img src={...}>`. No blob URLs, no caching, no streaming.
