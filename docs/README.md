# Avroom Documentation

Welcome to the Avroom architecture documentation. These docs describe the **current state** of the project as found in the code (not aspirational design).

> Last refresh: 2026-09-02

What changed in this refresh:

- Locked product language in [`CONTEXT.md`](../CONTEXT.md): Room (not session), Origin Photo, Room Selector / Room Upload / Room Workspace / Debug Dashboard, Object Selector, Copy, Source Cutout, 3D render, add object.
- Updated [overview.md](overview.md) glossary to point at `CONTEXT.md` and map domain words onto code identifiers.
- Updated frontend user-flow, overview, README, and components to use those names (code symbols such as `DashboardScreen` / `ObjectRail` stay in backticks).

Previous refresh (2026-08-24):

- Removed novel-view's HTTP-layer pose snapping (10° grid, azimuth wrap) and its per-`(uid, object_id, azimuth, elevation)` disk cache (`{uid}_{id}_novel_az{az}_el{el}.png` + `.preview.png`, and the now-deleted `core/novel_view_cache.py` module and `POST /images/novel-view/preview-cache` endpoint). `MeshRenderNovelViewStrategy` renders cheaply enough that every request now renders the exact requested pose fresh — see [backend/api-endpoints.md](backend/api-endpoints.md#post-imagesnovel-view), [ai-pipeline/ai-engines/novel-view/](ai-pipeline/ai-engines/novel-view/).

Previous refresh (2026-08-22):

- Depth rescale / smart-paste are UI-only: server persists `display_scale` + `average_depth`; cutout PNG stays pristine.
- Updated rescale/smart-paste API responses (no `cutout_b64`; added `display_scale`).
- Frontend renders objects at `displayScale` via CSS transform; session restore reads `display_scale` from `ObjectInfo`.
- Corrected the 3D reconstruction backend across every doc that named one: `Reconstruction3DFacade`'s default primary strategy is now **`Hunyuan3D2ReconstructionStrategy`** (Hugging Face Space `es3d-fi/hunyuan3d-2-1`, a mirror of `tencent/Hunyuan3D-2.1`, via `gradio_client`), with automatic fallback to **`TriposrReconstructionStrategy`** on failure — not TripoSR-as-default and not Trellis. See [ai-pipeline/ai-engines/reconstruction-3d/README.md](ai-pipeline/ai-engines/reconstruction-3d/README.md).
- Corrected the wiring status of 3D reconstruction: it **is** invoked in production, via `core/inference_pool`'s `JobKind.GENERATE_3D` from `POST /3d/test-3d` and `POST /images/novel-view` — previous docs said it was test-only / not on any HTTP path.
- Noted `TrellisReconstructionStrategy` and `Vfusion3dReconstructionStrategy` are optional backends reachable only by explicit injection — never constructed by the facade's default or fallback path.
- Noted Hunyuan3D-2.1 and TripoSR each map `ReconstructionQuality` via their own local tables, not the shared `GenerationParams`/`PRESETS` dict (that table is Trellis-specific).
- Updated `docs/presentation-plan.md` slide 5c to screenshot the Hunyuan3D-2.1 strategy (the backend actually running) instead of the unused Trellis strategy.

Previous refresh (2026-08-14):

- Documented the entire `/debug` router for the first time (it existed on the backend before this refresh but had no docs coverage): `POST /debug/validate`, `POST /debug/depth-map`, `POST /debug/sam-everything` — see [backend/api-endpoints.md](backend/api-endpoints.md#debug-endpoints), [backend/schemas.md](backend/schemas.md#debug), and the `DEBUG_ENDPOINTS` gate in [backend/settings-and-storage.md](backend/settings-and-storage.md).
- Documented the new Pipeline Debug screen (`DebugScreen`), reachable from the dashboard header's flask icon: [frontend/components.md](frontend/components.md#debugscreen), [frontend/user-flow.md](frontend/user-flow.md#pipeline-debug-screen), [frontend/api-integration.md](frontend/api-integration.md#debug-endpoints), [frontend/state-and-types.md](frontend/state-and-types.md#typesdebugts), [frontend/styling.md](frontend/styling.md).
- Documented `ImageValidator.validate_all` (runs every technical check without early-exit, unlike `validate()`) and SAM `predict_everything`/`get_all_masks_for_image` (prompt-free segmentation, added for the debug endpoints) plus its new quality-threshold params — see [ai-pipeline/ai-engines/segmentation/contracts.md](ai-pipeline/ai-engines/segmentation/contracts.md) and [components.md](ai-pipeline/ai-engines/segmentation/components.md).
- Documented `TestModules/src/utils/mask_visualizer.py` (`distinct_color`, `colorize_depth`, `overlay_masks`) — [ai-pipeline/utils/components.md](ai-pipeline/utils/components.md).
- Fixed a stale line-number reference to the CORS middleware block in `main.py` (moved when `expose_headers` was added) and fixed a dead link to a nonexistent `.cursor/skills/` path in this file.

If you change architecture, run the `update-docs` skill (see [`CLAUDE.md`](../CLAUDE.md) for how skills are invoked in this repo) to keep these files in sync with the code.

## How detail increases (pyramid)

Reading depth is intentional:

- **Root shared docs** ([overview.md](overview.md), [architecture.md](architecture.md), [data-flow.md](data-flow.md), [tech-stack.md](tech-stack.md), [repo-structure.md](repo-structure.md), [conventions.md](conventions.md)) explain what the system is, how tiers connect, and global rules. They stay relatively high level. Product language is in [`CONTEXT.md`](../CONTEXT.md).
- **Per-tier folders** ([backend/](backend/README.md), [frontend/](frontend/README.md), [ai-pipeline/](ai-pipeline/README.md)) add structure: what lives where in that tier’s code and which doc partials to open next.
- **Leaf partials** under each subsystem (`components.md`, `flow.md`, `contracts.md`, `operations.md`) are the most technical: current behavior, data steps, and operational knobs for that slice only.

Start at the root for orientation; drill into partials when you are implementing or debugging a specific component.

## How to read these docs

The docs are split into a small set of **shared** documents that describe the system as a whole, plus three **per-component** folders. Each folder is a self-contained mini-book covering one tier:

```
docs/
├── README.md            <- you are here
├── overview.md          - what Avroom is and what it does today
├── architecture.md      - 3-tier component picture + cross-cutting patterns
├── data-flow.md         - end-to-end click sequence
├── tech-stack.md        - languages, frameworks, models, versions
├── repo-structure.md    - annotated tour of the repo
├── conventions.md       - design patterns, naming, debug artifacts
├── docs-map.md          - quick index of where to find what
├── backend/             - FastAPI service in fastApi-app/
├── frontend/            - React SPA in react-front/
└── ai-pipeline/         - avroom_object_removal package in TestModules/
```

Product language (Room, Origin Photo, Cutout, …) lives in [`CONTEXT.md`](../CONTEXT.md) at the repo root, not under `docs/`.

AI pipeline docs: each subsystem folder has a short **README** (overview); deeper topics live in **partial** markdown files linked from that README (see [ai-pipeline/overview-vs-partials.md](ai-pipeline/overview-vs-partials.md)).

## Shared docs

- [CONTEXT.md](../CONTEXT.md) — product language (Room, Origin Photo, Cutout, Copy, …).
- [overview.md](overview.md) — project goal, MVP scope, glossary (maps onto `CONTEXT.md`).
- [architecture.md](architecture.md) — three-tier diagram and how the tiers talk to each other.
- [data-flow.md](data-flow.md) — sequence diagram of one full click → background + cutout request.
- [tech-stack.md](tech-stack.md) — runtime versions of every meaningful dependency.
- [repo-structure.md](repo-structure.md) — what each top-level folder is for.
- [conventions.md](conventions.md) — design patterns and project-wide conventions.
- [docs-map.md](docs-map.md) — where to find what.

## Per-component docs

| Component                             | Code root                       | Docs                                           |
| ------------------------------------- | ------------------------------- | ---------------------------------------------- |
| Frontend SPA                          | [react-front/](../react-front/) | [frontend/README.md](frontend/README.md)       |
| FastAPI backend                       | [fastApi-app/](../fastApi-app/) | [backend/README.md](backend/README.md)         |
| AI pipeline (`avroom_object_removal`) | [TestModules/](../TestModules/) | [ai-pipeline/README.md](ai-pipeline/README.md) |

## Source of truth

If a doc disagrees with the code, the code wins — and the docs are stale. Run the update skill (see top of this file).
