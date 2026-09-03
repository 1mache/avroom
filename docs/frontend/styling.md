# Styling

The frontend uses **plain global CSS** — no Tailwind, no CSS modules, no styled-components, no preprocessors.

## Single stylesheet

[`react-front/src/style.css`](../../react-front/src/style.css) (~1780 lines) is imported once in [`react-front/src/main.tsx`](../../react-front/src/main.tsx) and applies globally. The app is **dark-only** — `index.html` sets `<meta name="color-scheme" content="dark">` and there is no light-theme variant.

## Design tokens

All defined once on `:root`:

```css
:root {
  /* graphite chrome scale */
  --chrome-void: #161616;
  --chrome-bar: #242424;
  --chrome-panel: #2b2b2b;
  --chrome-raise: #383838;
  --chrome-line: #3f3f3f;
  --chrome-sunk: #1c1c1c;

  /* ink (text) scale */
  --ink: #d9d9d9;
  --ink-dim: #8b8b8b;
  --ink-faint: #616161;

  /* accent */
  --cyan: #16b3b8;
  --cyan-bright: #45e0e5;
  --cyan-wash: rgba(22, 179, 184, 0.14);
  --danger: #e2564f;

  /* layout */
  --toolbar-h: 44px;
  --rail-w: 214px;
  --rail-edge: 26px;

  /* type */
  --sans: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", "Cascadia Code", ui-monospace, monospace;
}
```

IBM Plex Sans (UI text) and IBM Plex Mono (counters/status readouts) are loaded from Google Fonts in [`index.html`](../../react-front/index.html), not in this file. A `--checker` token (a 4-layer diagonal-stripe gradient tuned for dark surfaces) backs cutout thumbnails and mask previews wherever transparency needs to read clearly. Radii stay at 2–3px throughout; there is no border-radius token, values are set per-rule.

## Section map

The file is organized into comment-delimited sections (`/* ── Name ── */`), roughly in this order:

| Section | Owner component(s) |
|---|---|
| Reset + scrollbar | global |
| Toolbar | `Toolbar` — `.toolbar`, `.session-name`, `.tool-btn`/`.tool-switch` (`.is-armed`, `.is-danger`, disabled greyed state), `.tool-spinner` |
| Tooltips | shared — `[data-tip]` CSS-only hover tooltip (0.32s delay); `.rail-action[data-tip]` opens leftward since the rail sits at the right edge |
| Stage | `WorkspaceScreen` — `.stage`, `.stage-zoom` (hold-Control focus scale), `.stage-photo` (`object-fit: contain`), `.stage-canvas-edge` (hairline + shadow), `.stage-cutout` (`pointer-events: none`), `.stage-input` (the real pointer owner), `.stage-pick-marker`, `.selection-frame`/`.selection-corner`, `.stage-hint`, `.stage-message` |
| Conflict notices | `WorkspaceScreen` via `useConflictNotices` — `.notice-stack`, `.notice`, `.notice-dismiss` |
| Object rail | `ObjectRail` — `.rail-spine`/`.rail-notch` (`is-selected`/`is-hidden`/`is-working`), `.rail-panel`, `.rail-row`, `.rail-thumb` (checkerboard background), `.rail-name`/`.rail-name-input`, `.rail-action`, `.rail-empty` |
| Modals | `ConfirmDialog`, `MaskPickerModal`, inline error modals — `.modal-backdrop`, `.modal` (`.is-masks`/`.is-error` size variants), `.mask-grid`/`.mask-card` |
| 3D angle picker | `Model3DFrame` — `.model-3d-frame`, `.model-3d-viewport` (cyan grid background) |
| Dashboard | `DashboardScreen`, `SessionCard` — `.dashboard`, `.dash-header`/`.dash-logo`/`.dash-wordmark`, `.session-grid`/`.session-card`/`.session-card-frame` (same hairline+shadow treatment as the stage canvas), `.session-card-delete` (hover-reveal), `.session-skeleton` loading shimmer |
| Upload | `UploadScreen` — `.dropzone` (`.is-over`/`.has-file`), `.dropzone-preview`, `.upload-status`, `.upload-rejection`, `.upload-rules` |
| Buttons & confirm dialog | `ConfirmDialog` — `.btn` (`.is-primary`/`.is-danger`), `.modal.is-confirm`, `.confirm-title`/`.confirm-body`/`.confirm-actions` |
| Pipeline debug | `DebugScreen` — `.dash-header-end` (right-aligned header slot), `.debug-scroll`/`.debug-source`/`.debug-dropzone` (reuses `.dropzone*`), `.debug-panel`/`.debug-panel-head`/`.debug-verdict` (`.is-pass`/`.is-fail`), `.debug-check-row`/`.debug-check-dot`/`.debug-check-group` (validation scoreboard), `.debug-knobs`/`.debug-knob` (per-panel controls), `.debug-image-frame` (checkerboard-backed rendered PNG, `cursor: zoom-in`), `.debug-lightbox-backdrop`/`.debug-lightbox-img` (full-screen viewer, reuses `.modal-backdrop`) |
| Narrow screens | `@media (max-width: 720px)` — shrinks `--rail-w`, dashboard/grid paddings, forces `.session-card-delete` always visible (no hover on touch), hides `.toolbar-status` |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` — collapses all animation/transition durations to 0.01ms |

## When to add styles

Add to the same file, in the section that matches the owning component. Don't introduce CSS modules / Tailwind / etc. without a stronger reason than "more components" — a single stylesheet has stayed tractable through the dashboard/workspace redesign. If it keeps growing, the next sensible step is splitting by component (one file per `.tsx`) before reaching for a framework.
