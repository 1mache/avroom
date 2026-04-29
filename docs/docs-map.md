# Docs map (where to look)

This page is a quick index to help you find information fast. If you change code behavior, update the specific page that documents it (and then bump `docs/README.md`'s refresh date).

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
  - How README vs partial pages fit together: [`ai-pipeline/overview-vs-partials.md`](ai-pipeline/overview-vs-partials.md)
  - Core orchestration (`TestModules/src/core/`): [`ai-pipeline/core/README.md`](ai-pipeline/core/README.md) — partials: [`components`](ai-pipeline/core/components.md), [`flow`](ai-pipeline/core/flow.md), [`contracts`](ai-pipeline/core/contracts.md), [`operations`](ai-pipeline/core/operations.md)
  - Engine domains (`TestModules/src/ai_engines/`): [`ai-pipeline/ai-engines/README.md`](ai-pipeline/ai-engines/README.md) — partials: [`components`](ai-pipeline/ai-engines/components.md), [`flow`](ai-pipeline/ai-engines/flow.md), [`contracts`](ai-pipeline/ai-engines/contracts.md), [`operations`](ai-pipeline/ai-engines/operations.md)
    - Depth: [`ai-pipeline/ai-engines/depth/README.md`](ai-pipeline/ai-engines/depth/README.md) — partials: [`components`](ai-pipeline/ai-engines/depth/components.md), [`flow`](ai-pipeline/ai-engines/depth/flow.md), [`contracts`](ai-pipeline/ai-engines/depth/contracts.md), [`operations`](ai-pipeline/ai-engines/depth/operations.md)
    - Segmentation: [`ai-pipeline/ai-engines/segmentation/README.md`](ai-pipeline/ai-engines/segmentation/README.md) — partials: [`components`](ai-pipeline/ai-engines/segmentation/components.md), [`flow`](ai-pipeline/ai-engines/segmentation/flow.md), [`contracts`](ai-pipeline/ai-engines/segmentation/contracts.md), [`operations`](ai-pipeline/ai-engines/segmentation/operations.md)
    - Inpainting: [`ai-pipeline/ai-engines/inpainting/README.md`](ai-pipeline/ai-engines/inpainting/README.md) — partials: [`components`](ai-pipeline/ai-engines/inpainting/components.md), [`flow`](ai-pipeline/ai-engines/inpainting/flow.md), [`contracts`](ai-pipeline/ai-engines/inpainting/contracts.md), [`operations`](ai-pipeline/ai-engines/inpainting/operations.md)
    - Reconstruction 3D: [`ai-pipeline/ai-engines/reconstruction-3d/README.md`](ai-pipeline/ai-engines/reconstruction-3d/README.md) — partials: [`components`](ai-pipeline/ai-engines/reconstruction-3d/components.md), [`flow`](ai-pipeline/ai-engines/reconstruction-3d/flow.md), [`contracts`](ai-pipeline/ai-engines/reconstruction-3d/contracts.md), [`operations`](ai-pipeline/ai-engines/reconstruction-3d/operations.md)
  - Routing layer (`TestModules/src/routing/`): [`ai-pipeline/routing/README.md`](ai-pipeline/routing/README.md) — partials: [`components`](ai-pipeline/routing/components.md), [`flow`](ai-pipeline/routing/flow.md), [`contracts`](ai-pipeline/routing/contracts.md), [`operations`](ai-pipeline/routing/operations.md)
  - Utilities (`TestModules/src/utils/`): [`ai-pipeline/utils/README.md`](ai-pipeline/utils/README.md) — partials: [`components`](ai-pipeline/utils/components.md), [`flow`](ai-pipeline/utils/flow.md), [`contracts`](ai-pipeline/utils/contracts.md), [`operations`](ai-pipeline/utils/operations.md)
  - Test scripts (`TestModules/tests/`): [`ai-pipeline/tests/README.md`](ai-pipeline/tests/README.md) — partials: [`components`](ai-pipeline/tests/components.md), [`flow`](ai-pipeline/tests/flow.md), [`contracts`](ai-pipeline/tests/contracts.md), [`operations`](ai-pipeline/tests/operations.md)

