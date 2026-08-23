# Project Overview

## What Avroom is

Avroom is an AI-powered application for **selecting and removing furniture / objects from room images** and inpainting the missing background so the result looks like the object was never there.

The user clicks once on an object in a room photo, and Avroom returns:

1. The room image with the object removed and the background plausibly filled in (the **background**).
2. A transparent cutout of the clicked object on its own (the **cutout**).

## MVP scope (today)

The current MVP exposes a multi-object interactive flow across two screens (dashboard + workspace, no auth):

1. Frontend uploads a room image to the backend from the upload screen.
2. Frontend lets the user click an object to remove, in the workspace.
3. Backend segments the click against the current canvas (previous removals already applied), returns mask candidates, user picks one, backend inpaints and returns the updated background plus a numbered cutout (`{uid}_{object_id}_cutout.png`).
4. User can add more objects by re-arming the cutout tool and clicking again; each removal stacks on the previous result. Objects can also be dragged, duplicated, deleted, and rotated (2D novel-view synthesis) via the `ObjectRail` right-edge panel and the workspace toolbar.
5. Each session can have multiple processed objects, each with an optional 3D model and a dashboard preview thumbnail.

There is **no** auth and no multi-user state. 3D reconstruction is not part of the `/images/*` click/inpaint flow, but the `avroom_object_removal` package's `Reconstruction3DFacade` is wired into two separate endpoints — `POST /3d/test-3d` and `POST /images/novel-view` — via `core/inference_pool`: by default it uses **Hunyuan3D-2.1** (`Hunyuan3D2ReconstructionStrategy`, a Hugging Face Space via `gradio_client`), automatically falling back to **TripoSR** (`TriposrReconstructionStrategy`) if the Space call fails; other strategies (OpenLRM, Trellis, VFusion3D) can be injected explicitly — see [ai-pipeline/ai-engines/reconstruction-3d/README.md](ai-pipeline/ai-engines/reconstruction-3d/README.md). There is also no batch / async workflow yet.

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
| **object_id** | Zero-based integer assigned to each finalized object within a session (0, 1, 2 …). Used in storage filenames (`{uid}_{object_id}_cutout.png`) and in `InpaintMaskResponse`. |
| **canvas** | The cumulative inpainted background (`{uid}_background.png`). Each inpaint overwrites it; new segmentations read from it, so removals stack progressively. |
| **session** | One uploaded image plus all objects removed from it. Identified by a UUID (`uid`). |

## Historical context

The earlier project notes live at [`avroom_context.md`](../avroom_context.md). They describe the same goals but predate the current implementation; in case of conflict, the docs in this folder reflect the actual code.
