# Avroom Documentation

Welcome to the Avroom architecture documentation. These docs describe the **current state** of the project as found in the code (not aspirational design).

> Last refresh: 2026-08-07

What changed in this refresh:

- Frontend: full rewrite of `frontend/` docs — they described the pre-redesign single-`MainPage` SPA (`UploadFrame`/`ResultFrame`/`ObjectPanel`/`SessionPicker`), which no longer exists. Now documents the real two-screen app: `App.tsx`'s local route switch (dashboard / upload / workspace, no router library), `DashboardScreen` + `UploadScreen` + `WorkspaceScreen`, the `Toolbar`/`ObjectRail` workspace chrome, and the three session hooks (`useSessionJobs`, `useSessionSync`, `useConflictNotices`).
- Frontend: documented drag-to-reposition, object duplication, object deletion, 2D rotation (novel-view), and dashboard preview thumbnails end-to-end on the frontend side (backend side was already current).
- Fixed a stale fact repeated in `CLAUDE.md` and `backend/api-endpoints.md`: the dashboard-preview debounce is 500ms (`PREVIEW_DEBOUNCE_MS`), not ~1.5s.
- Fixed a stale architecture claim in `CLAUDE.md`'s Frontend Notes: the dashboard and upload screens exist and are wired up (they were previously described as "not yet built"); the workspace back arrow is enabled, not disabled.
- Removed dead frontend code ahead of this refresh: the `clickImage` API wrapper (unused `POST /images/click` client), the unused `SessionSyncCheckRequest` TS type, and an orphaned `.stage-message-hint` CSS rule — `docs/frontend/api-integration.md` updated to match.
- Root docs (`overview.md`, `data-flow.md`, `repo-structure.md`, `architecture.md`) had their remaining `MainPage`/`ObjectPanel`/`UploadFrame` references replaced.

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
