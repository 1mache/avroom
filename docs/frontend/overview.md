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

Runtime deps are intentionally minimal: React + Three.js only. There is no router, no state library, no HTTP client, and no styling framework.

## TypeScript config

From [`react-front/tsconfig.json`](../../react-front/tsconfig.json):

- `strict: true` plus `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`, `noUncheckedSideEffectImports`, `erasableSyntaxOnly`.
- `jsx: "react-jsx"`, `module: "ESNext"`, `moduleResolution: "bundler"`, target/lib `ES2023` + `DOM`.
- `noEmit: true` — building is done by Vite; `tsc` only type-checks.
- `include: ["src"]`, no `paths` aliases.

## Bootstrap

```1:11:react-front/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import "./style.css";

ReactDOM.createRoot(document.getElementById("app") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

The mount point is `#app` (declared in [`react-front/index.html`](../../react-front/index.html) lines 10–11). The global stylesheet is imported here once.

`App` is just a wrapper:

```1:7:react-front/src/App.tsx
import React from "react";

import { MainPage } from "./components/layout/MainPage";

export const App: React.FC = () => {
  return <MainPage />;
};
```

## File layout

```
react-front/
├── index.html
├── package.json
├── tsconfig.json
├── public/                      - favicon.svg, icons.svg
└── src/
    ├── main.tsx                 - React root
    ├── App.tsx                  - composition root
    ├── style.css                - global styles
    ├── api/images.ts            - backend HTTP wrappers
    ├── types/api.ts             - mirrored Pydantic models
    ├── components/
    │   ├── layout/MainPage.tsx
    │   └── widgets/
    │       ├── UploadFrame.tsx
    │       └── ResultFrame.tsx
    ├── assets/                  - hero.png, vite.svg, typescript.svg
    └── counter.ts               - leftover from Vite scaffold; not imported
```

## Routing

There is none — `App` always renders `MainPage`. Treat the SPA as a single screen.

## Run / build

From `react-front/`:

```bash
npm install
npm run dev       # vite dev server on :5173
npm run build     # tsc + vite build, emits dist/
npm run preview   # preview the prod build
```

For the dev server to work end-to-end, the backend on `http://127.0.0.1:8000` must be running, and its CORS list must include `http://localhost:5173` / `http://127.0.0.1:5173` (already configured — see [backend/overview.md](../backend/overview.md)).
