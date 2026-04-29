# Avroom Documentation

Welcome to the Avroom architecture documentation. These docs describe the **current state** of the project as found in the code (not aspirational design).

> Last refresh: 2026-04-29

What changed in this refresh:

- Added docs for the standalone Trellis image-to-3D package (`TrellisModule/`).
- Added a short docs map page (`docs-map.md`) to speed up future searches.
- Updated repo structure / tech stack / overview to reflect the Trellis module and install wiring.

If you change architecture, run the [`update-avroom-docs`](../.cursor/skills/update-avroom-docs/SKILL.md) skill to keep these files in sync with the code.

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
├── backend/             - FastAPI service in fastApi-app/
├── frontend/            - React SPA in react-front/
└── ai-pipeline/         - avroom_object_removal package in TestModules/
```

## Shared docs

- [overview.md](overview.md) — project goal, MVP scope, glossary.
- [architecture.md](architecture.md) — three-tier diagram and how the tiers talk to each other.
- [data-flow.md](data-flow.md) — sequence diagram of one full click → background + cutout request.
- [tech-stack.md](tech-stack.md) — runtime versions of every meaningful dependency.
- [repo-structure.md](repo-structure.md) — what each top-level folder is for.
- [conventions.md](conventions.md) — design patterns and project-wide conventions.
- [docs-map.md](docs-map.md) — where to find what.
- [trellis-module.md](trellis-module.md) — `avroom_trellis` image-to-3D wrapper (not wired into the main flow).

## Per-component docs

| Component | Code root | Docs |
|---|---|---|
| Frontend SPA | [react-front/](../react-front/) | [frontend/README.md](frontend/README.md) |
| FastAPI backend | [fastApi-app/](../fastApi-app/) | [backend/README.md](backend/README.md) |
| AI pipeline (`avroom_object_removal`) | [TestModules/](../TestModules/) | [ai-pipeline/README.md](ai-pipeline/README.md) |

## Source of truth

If a doc disagrees with the code, the code wins — and the docs are stale. Run the update skill (see top of this file).
