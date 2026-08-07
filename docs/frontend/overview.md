# Frontend Overview

## Tooling

From [`react-front/package.json`](../../react-front/package.json):

| | |
|---|---|
| Framework | React 19 (`^19.2.4`) + ReactDOM |
| Build / dev | Vite 5 (`^5.4.0`) |
| Type checker | TypeScript `~5.9.3` |
| Module type | ESM (`"type": "module"`) |
| Scripts | `dev` (vite), `build` (`tsc && vite build`), `preview` |

Runtime deps are intentionally minimal: React + Three.js only. There is no router library, no state library, no HTTP client, and no CSS framework.

## TypeScript config

From [`react-front/tsconfig.json`](../../react-front/tsconfig.json):

- `strict: true` plus `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, `noUncheckedSideEffectImports`, `erasableSyntaxOnly`.
- `jsx: "react-jsx"`, `module: "ESNext"`, `moduleResolution: "bundler"`, target/lib `ES2023` + `DOM`.
- `noEmit: true` — building is done by Vite; `tsc` only type-checks.
- `include: ["src"]`, no `paths` aliases.

## Bootstrap

```1:14:react-front/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import "./style.css";

// StrictMode helps catch effect/cleanup mistakes in interactive widgets like
// upload preview, drag listeners, and Three.js mount lifecycle.
ReactDOM.createRoot(document.getElementById("app") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

The mount point is `#app` ([`react-front/index.html`](../../react-front/index.html) line 17). The global stylesheet is imported here once. `index.html` also loads IBM Plex Sans / IBM Plex Mono from Google Fonts and sets `<meta name="color-scheme" content="dark">` — the app is dark-only, no light theme.

## Routing

There is no router library. [`App.tsx`](../../react-front/src/App.tsx) holds a local discriminated union and renders exactly one screen from it:

```10:37:react-front/src/App.tsx
type Route =
  | { screen: "dashboard" }
  | { screen: "upload" }
  | { screen: "workspace"; uid: string };

export const App: React.FC = () => {
  const [route, setRoute] = useState<Route>({ screen: "dashboard" });

  const openSession = useCallback((uid: string) => setRoute({ screen: "workspace", uid }), []);
  const goToDashboard = useCallback(() => setRoute({ screen: "dashboard" }), []);

  if (route.screen === "workspace") {
    // Keyed by uid so switching sessions remounts the workspace rather than
    // leaving one session's objects, geometry and in-flight jobs behind.
    return <WorkspaceScreen key={route.uid} uid={route.uid} onExit={goToDashboard} />;
  }

  if (route.screen === "upload") {
    return <UploadScreen onCancel={goToDashboard} onUploaded={openSession} />;
  }

  return (
    <DashboardScreen
      onOpenSession={openSession}
      onNewSession={() => setRoute({ screen: "upload" })}
    />
  );
};
```

`App` boots into `{screen: "dashboard"}`. `DashboardScreen`'s "New session" CTA moves to `upload`; `UploadScreen`'s success callback (`onUploaded`) and a `SessionCard` click both move to `workspace` with a `uid`. `WorkspaceScreen`'s back arrow (`onExit`) and `UploadScreen`'s cancel both return to `dashboard`. Mounting `WorkspaceScreen` with `key={route.uid}` means switching sessions unmounts and remounts the whole editor rather than reusing state across sessions.

## File layout

```
react-front/
├── index.html
├── package.json
├── tsconfig.json
├── public/                          - favicon.svg, icons.svg, avroom.png (tab icon)
└── src/
    ├── main.tsx                     - React root
    ├── App.tsx                      - route switch: dashboard / upload / workspace
    ├── style.css                    - single global stylesheet
    ├── assets/avroom.png            - logo used in the dashboard header
    ├── api/images.ts                - backend HTTP wrappers
    ├── types/
    │   ├── api.ts                   - mirror of backend Pydantic models
    │   └── session.ts               - client-only view models (CutoutObject, rotation, etc.)
    ├── hooks/
    │   ├── useSessionJobs.ts        - objects, selection, segment/inpaint/duplicate/delete/rotate/rename
    │   ├── useSessionSync.ts        - polling + focus/visibility reconcile against server truth
    │   └── useConflictNotices.ts    - turns 409s into dismissible inline notices
    ├── utils/
    │   ├── stageGeometry.ts         - contain-fit / natural-pixel / hit-test math
    │   ├── preview.ts               - dashboard thumbnail compositing
    │   └── time.ts                  - relative-time label, most-recently-edited sort
    └── components/
        ├── layout/
        │   ├── DashboardScreen.tsx  - session list, new-session entry, session delete
        │   ├── UploadScreen.tsx     - file intake (drag-drop or picker) between dashboard and workspace
        │   └── WorkspaceScreen.tsx  - the editor; owns most local state, composes the hooks
        ├── workspace/
        │   ├── Toolbar.tsx          - top chrome: back, session name, tools, trash
        │   └── ObjectRail.tsx       - right-edge object list (replaces the old ObjectPanel)
        ├── dashboard/
        │   └── SessionCard.tsx      - one dashboard grid tile
        ├── widgets/
        │   ├── ConfirmDialog.tsx    - shared confirm/cancel modal (session delete, object delete)
        │   ├── MaskPickerModal.tsx  - segmentation candidate picker
        │   └── Model3DFrame.tsx     - Three.js GLB viewer, doubles as the rotation angle picker
        └── icons.tsx                - shared inline SVG icon set
```

## Run / build

From `react-front/`:

```bash
npm install
npm run dev       # vite dev server on :5173
npm run build     # tsc + vite build, emits dist/
npm run preview   # preview the prod build
```

For the dev server to work end-to-end, the backend on `http://127.0.0.1:8000` must be running, and its CORS list must include `http://localhost:5173` / `http://127.0.0.1:5173` (already configured — see [backend/overview.md](../backend/overview.md)).
