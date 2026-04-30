# Project Overview

## What Avroom is

Avroom is an AI-powered application for **selecting and removing furniture / objects from room images** and inpainting the missing background so the result looks like the object was never there.

The user clicks once on an object in a room photo, and Avroom returns:

1. The room image with the object removed and the background plausibly filled in (the **background**).
2. A transparent cutout of the clicked object on its own (the **cutout**).

## MVP scope (today)

The current MVP, end-to-end, exposes a single interactive flow:

1. Frontend uploads a room image to the backend.
2. Frontend lets the user click the object to remove.
3. Backend runs the AI pipeline and returns two base64-encoded PNGs (background + cutout) which the frontend renders.

There is **no** auth, no multi-user state, and no 3D reconstruction in the live `/images/*` pipeline. The `avroom_object_removal` package does ship a `Reconstruction3DFacade` for optional image-to-3D (GLB): it **defaults** to local **OpenLRM** (`OpenLrmReconstructionStrategy`); **Trellis** on Hugging Face Spaces remains available by injecting `TrellisReconstructionStrategy` — see [ai-pipeline/ai-engines/reconstruction-3d/README.md](ai-pipeline/ai-engines/reconstruction-3d/README.md). It is **not wired into** the HTTP flow today; only the smoke test exercises it. There is also no batch / async workflow yet.

## High-level design

Avroom is a three-tier system:

- **Frontend** — a React 19 + Vite SPA in [react-front/](../react-front/).
- **Backend** — a FastAPI service in [fastApi-app/](../fastApi-app/).
- **AI pipeline** — a Python package `avroom_object_removal` in [TestModules/](../TestModules/), installed editable from the root `requirements.txt` and imported in-process by the backend.

See [architecture.md](architecture.md) for the diagram and connection details.

## Glossary

| Term | Meaning |
|---|---|
| **image_id** | Server-generated UUID used to reference an uploaded image on subsequent requests. |
| **click coordinates** | `(x, y)` pixel coordinates on the **natural** (un-scaled) image, origin at top-left. |
| **background** | Original image with the clicked object removed and the hole inpainted. |
| **cutout** | Transparent PNG containing only the clicked-object pixels (BGRA, alpha=0 outside the mask). |
| **depth map** | Single-channel image where pixel intensity encodes how near (bright) or far (dark) the pixel is from the camera. Used by SAM as input instead of RGB. |
| **mask** | Binary image where non-zero pixels mark the object to be removed. |
| **router / routing strategy** | Component that decides how to feed SAM and how aggressively to expand its output, based on local depth statistics around the click. |
| **hybrid inpainter** | LaMa first, then optional Stable Diffusion refinement (skipped when SD strength is low). |

## Historical context

The earlier project notes live at [`avroom_context.md`](../avroom_context.md). They describe the same goals but predate the current implementation; in case of conflict, the docs in this folder reflect the actual code.
