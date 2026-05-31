# Avroom Documentation

Welcome to the Avroom architecture documentation. These docs describe the **current state** of the project as found in the code (not aspirational design).

> Last refresh: 2026-06-01

What changed in this refresh:

- Backend: new `POST /images/{uid}/name` endpoint; `GET /images/sessions` now returns `list[SessionInfo]` (was `list[str]`); `GET /images/{uid}/cache` now includes `name` field — updated `api-endpoints.md`.
- Backend: added `SessionInfo`, `SetNameRequest` models; added `name` field to `UidCacheStatusResponse` — updated `schemas.md`.
- Backend: added `get_names_file()`, `load_names()`, `set_session_name()` to `settings.py`; documented `names.json` storage layout; fixed `register_uid` line reference (104–121) — updated `settings-and-storage.md`.
- Frontend: `getSessions()` returns `SessionInfo[]`; added `setSessionName()` API function — updated `api-integration.md`.
- Frontend: added `sessionName` and `sessionsRefreshKey` state; added `SessionInfo` type; updated `UidCacheStatusResponse` with `name?` — updated `state-and-types.md`.
- Frontend: `SessionPicker` now accepts `refreshKey` prop and shows custom names on chips; `MainPage` has editable session name field — updated `components.md`.

If you change architecture, run the [`update-avroom-docs`](../.cursor/skills/update-avroom-docs/SKILL.md) skill to keep these files in sync with the code.

## How detail increases (pyramid)

Reading depth is intentional:

- **Root shared docs** ([overview.md](overview.md), [architecture.md](architecture.md), [data-flow.md](data-flow.md), [tech-stack.md](tech-stack.md), [repo-structure.md](repo-structure.md), [conventions.md](conventions.md)) explain what the system is, how tiers connect, and global rules. They stay relatively high level.
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

AI pipeline docs: each subsystem folder has a short **README** (overview); deeper topics live in **partial** markdown files linked from that README (see [ai-pipeline/overview-vs-partials.md](ai-pipeline/overview-vs-partials.md)).

## Shared docs

- [overview.md](overview.md) — project goal, MVP scope, glossary.
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
