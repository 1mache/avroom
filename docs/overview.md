# Project Overview

## What Avroom is

Avroom is an AI-powered application for **selecting and removing furniture / objects from room images** and inpainting the missing background so the result looks like the object was never there.

Product language lives in [`CONTEXT.md`](../CONTEXT.md). The user clicks a **segmentation seed** on an **Origin Photo** in a **Room**, and Avroom returns:

1. The room image with the object removed and the hole filled in (the **Background**).
2. A transparent PNG of the clicked object (the **Cutout**).

## MVP scope (today)

The current MVP exposes a multi-object interactive flow across **Room Selector**, **Room Upload**, and **Room Workspace** (no auth):

1. Frontend uploads an Origin Photo to the backend from Room Upload.
2. Frontend lets the user cut out an object in Room Workspace.
3. Backend segments the click against the current Background (previous removals already applied), returns mask candidates, user picks one, backend inpaints and returns the updated Background plus a numbered cutout (`{uid}_{object_id}_cutout.png`).
4. User can add more objects by re-arming the cutout tool and clicking again; each removal stacks on the previous result. Objects can also be dragged, copied, deleted, and rotated (2D novel-view synthesis) via the Object Selector (`ObjectRail`) and the workspace toolbar.
5. Each Room can have multiple processed objects, each with an optional 3D render and a Preview thumbnail on Room Selector.

There is **no** auth and no multi-user state. 3D reconstruction is not part of the `/images/*` click/inpaint flow, but the `avroom_object_removal` package's `Reconstruction3DFacade` is wired into two separate endpoints — `POST /3d/test-3d` and `POST /images/novel-view` — via `core/inference_pool`: by default it uses **Hunyuan3D-2.1** (`Hunyuan3D2ReconstructionStrategy`, a Hugging Face Space via `gradio_client`), automatically falling back to **TripoSR** (`TriposrReconstructionStrategy`) if the Space call fails; other strategies (OpenLRM, Trellis, VFusion3D) can be injected explicitly — see [ai-pipeline/ai-engines/reconstruction-3d/README.md](ai-pipeline/ai-engines/reconstruction-3d/README.md). There is also no batch / async workflow yet.

## High-level design

Avroom is a three-tier system:

- **Frontend** — a React 19 + Vite SPA in [react-front/](../react-front/).
- **Backend** — a FastAPI service in [fastApi-app/](../fastApi-app/).
- **AI pipeline** — a Python package `avroom_object_removal` in [TestModules/](../TestModules/), installed editable from the root `requirements.txt` and imported in-process by the backend.

See [architecture.md](architecture.md) for the diagram and connection details.

## Glossary

Product language (Room, Origin Photo, Cutout, Copy, Object Selector, …) is defined in [`CONTEXT.md`](../CONTEXT.md). Code still uses the identifiers below.

| Domain | Code still says |
|---|---|
| **Room** | `session`, `uid`, `image_id` |
| **Origin Photo** | original upload, `{uid}` original file |
| **Background** | canvas, `{uid}_background.png` |
| **Object Selector** | `ObjectRail` |
| **Copy** | duplicate, clone |
| **Add object** | import |
| **3D render** | GLB, `glbData` |
| **Source Cutout** | pristine cutout |
| **Segmentation seed** | seed, click point |
| **Room Selector / Room Upload / Room Workspace / Debug Dashboard** | `DashboardScreen` / `UploadScreen` / `WorkspaceScreen` / `DebugScreen` |

| Pipeline term | Meaning |
|---|---|
| **click coordinates** | `(x, y)` in **natural-image** (Origin Photo pixels, origin top-left). |
| **depth map** | Single-channel image where pixel intensity encodes how near (bright) or far (dark) the pixel is from the camera. Used by SAM as input instead of RGB. |
| **router / routing strategy** | Component that decides how to feed SAM and how aggressively to expand its output, based on local depth statistics around the click. |
| **hybrid inpainter** | LaMa first, then optional Stable Diffusion refinement (skipped when SD strength is low). |
| **object_id** | Zero-based integer assigned to each finalized object within a room (0, 1, 2 …). Used in storage filenames (`{uid}_{object_id}_cutout.png`) and in `InpaintMaskResponse`. |

## Historical context

The earlier project notes live at [`avroom_context.md`](../avroom_context.md). They describe the same goals but predate the current implementation; in case of conflict, the docs in this folder reflect the actual code.
