# Docs map (where to look)

This page is a quick index to help you find information fast. If you change code behavior, update the specific page that documents it (and then bump `docs/README.md`’s refresh date).

## System-level docs (this folder)

- **What Avroom does today**: [`overview.md`](overview.md)
- **How the tiers fit together**: [`architecture.md`](architecture.md)
- **One end-to-end click, traced**: [`data-flow.md`](data-flow.md)
- **Versions + models + install sources**: [`tech-stack.md`](tech-stack.md)
- **What each repo folder is for**: [`repo-structure.md`](repo-structure.md)
- **Cross-cutting rules and patterns**: [`conventions.md`](conventions.md)

## Component docs

- **Backend (FastAPI)**: [`backend/README.md`](backend/README.md)
  - Endpoints: [`backend/api-endpoints.md`](backend/api-endpoints.md)
  - Schemas: [`backend/schemas.md`](backend/schemas.md)
  - Storage + settings: [`backend/settings-and-storage.md`](backend/settings-and-storage.md)
  - Backend→pipeline bridge: [`backend/core-image-processing.md`](backend/core-image-processing.md)

- **Frontend (React)**: [`frontend/README.md`](frontend/README.md)
  - API calls + env vars: [`frontend/api-integration.md`](frontend/api-integration.md)
  - State + TS types: [`frontend/state-and-types.md`](frontend/state-and-types.md)
  - Components: [`frontend/components.md`](frontend/components.md)
  - User flow: [`frontend/user-flow.md`](frontend/user-flow.md)

- **AI pipeline (`avroom_object_removal`)**: [`ai-pipeline/README.md`](ai-pipeline/README.md)
  - Pipeline stage order: [`ai-pipeline/object-remover.md`](ai-pipeline/object-remover.md)
  - Line-by-line pipeline trace: [`ai-pipeline/data-flow.md`](ai-pipeline/data-flow.md)
  - Debug outputs list: [`ai-pipeline/outputs.md`](ai-pipeline/outputs.md)

## “Not wired into the main flow” docs

- **Trellis image-to-3D wrapper (`avroom_trellis`)**: [`trellis-module.md`](trellis-module.md)
  - Standalone module + manual smoke test; not part of `fastApi-app/` endpoints.
- **Hunyuan3D stub (vendored upstream snapshot)**: [`ai-pipeline/3d-reconstruction-hunyuan.md`](ai-pipeline/3d-reconstruction-hunyuan.md)
  - Present in the repo but not used at runtime.

