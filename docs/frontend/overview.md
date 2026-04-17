# Frontend Overview

**Directory:** `react-front/`

## Purpose

The frontend is a minimal MVP UI that demonstrates the full click-to-remove workflow. It allows a user to upload a room photo, click on an object to remove, and view the inpainted background and the extracted object cutout side by side.

## Tech Stack

| Tool | Version Constraint | Role |
|---|---|---|
| Vite | See `package.json` | Build tool and dev server |
| React | 18+ | Component framework |
| TypeScript | See `tsconfig.json` | Type safety |

## Starting the Frontend

From the `react-front/` directory:

```powershell
npm install
npm run dev
```

The dev server starts at `http://localhost:5173`.

## API Base URL

Configured via the `VITE_API_BASE_URL` environment variable. If not set, defaults to `http://127.0.0.1:8000`. See [`api-client.md`](api-client.md).

## Application Structure

```
src/
├── main.tsx                     # React root — mounts <App /> into #root
├── App.tsx                      # Renders <MainPage /> only
├── style.css                    # Global styles
├── api/images.ts                # HTTP layer
├── types/api.ts                 # TypeScript types for API payloads
└── components/
    ├── layout/MainPage.tsx      # Page state + orchestration
    └── widgets/
        ├── UploadFrame.tsx      # Image display + click capture
        └── ResultFrame.tsx      # Result display
```

## User Flow

1. User clicks the upload area or selects a file → `UploadFrame` fires `onFileSelected`
2. `MainPage` stores the file and creates an object URL for preview
3. User clicks "Upload" → API call to `POST /images/upload` → `image_id` stored in state
4. User clicks on the displayed image → `UploadFrame` captures and converts to natural coords
5. User clicks "Run" → API call to `POST /images/click` → two base64 data URLs
6. `ResultFrame` components display the background and cutout

## Sub-documentation

- [`components.md`](components.md) — detailed component behavior
- [`api-client.md`](api-client.md) — HTTP wrapper functions and type mapping
