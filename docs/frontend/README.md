# Frontend Docs

The frontend is a React 19 + Vite 5 SPA in [`react-front/`](../../react-front/). It has no router library, no global state library, no CSS framework, and no HTTP library — just `fetch`, a handful of custom hooks, a single global `style.css`, and Three.js for GLB rendering.

There is no server-rendered routing: [`App.tsx`](../../react-front/src/App.tsx) switches between three screens with local component state. The **dashboard** is home (session list, new-session entry, session delete); **upload** is the file-intake step between dashboard and workspace; the **workspace** is the editor.

## Pages

- [overview.md](overview.md) — bootstrap, tooling, file layout, routing.
- [components.md](components.md) — `DashboardScreen`, `UploadScreen`, `WorkspaceScreen`, `Toolbar`, `ObjectRail`, `SessionCard`, and the shared widgets.
- [api-integration.md](api-integration.md) — how the SPA talks to the FastAPI backend.
- [state-and-types.md](state-and-types.md) — the three session hooks and the TypeScript type layers.
- [styling.md](styling.md) — design tokens and the global CSS approach.
- [user-flow.md](user-flow.md) — dashboard → upload → workspace, and every in-workspace flow (segment/inpaint, drag, duplicate, delete, rotate, session restore/sync).

## At a glance

```mermaid
flowchart TD
    main["main.tsx"] --> App["App.tsx<br/>Route state"]
    App -->|screen: dashboard| Dashboard["DashboardScreen"]
    App -->|screen: upload| Upload["UploadScreen"]
    App -->|screen: workspace, uid| Workspace["WorkspaceScreen key=uid"]
    Dashboard --> SessionCard["SessionCard"]
    Dashboard --> ConfirmDialogD["ConfirmDialog (delete session)"]
    Workspace --> Toolbar["Toolbar"]
    Workspace --> ObjectRail["ObjectRail"]
    Workspace --> MaskPickerModal["MaskPickerModal"]
    Workspace --> Model3DFrame["Model3DFrame (rotate mode)"]
    Workspace --> ConfirmDialogO["ConfirmDialog (delete object)"]
    Workspace --> hooks["useSessionJobs / useSessionSync<br/>useConflictNotices"]
    hooks --> apiImages["api/images.ts"]
    apiImages -->|fetch| Backend(("FastAPI<br/>VITE_API_BASE_URL"))
```
