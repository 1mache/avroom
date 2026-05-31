# Styling

The frontend uses **plain global CSS** — no Tailwind, no CSS modules, no styled-components, no preprocessors.

## Single stylesheet

[`react-front/src/style.css`](../../react-front/src/style.css) is imported once in [`react-front/src/main.tsx`](../../react-front/src/main.tsx) line 5 and applies globally.

## Approach

- A small set of CSS variables on `:root` defines the palette and the typography:

```1:16:react-front/src/style.css
:root {
  --text: #111827;
  --text-muted: #6b7280;
  --bg: #f3f4f6;
  --panel-bg: #ffffff;
  --border: #e5e7eb;
  --accent: #2563eb;
  --accent-soft: #dbeafe;
  --danger: #dc2626;

  --sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;

  font: 16px/1.5 var(--sans);
  color: var(--text);
  background-color: var(--bg);
}
```

- Component classes are utility-ish but not strict. Mask picker styles also live here: `.mask-modal-backdrop`, `.mask-modal`, `.mask-option-grid`, `.mask-option-card`, and `.mask-option-preview`.
- Responsive layout for small screens uses a single `@media (max-width: 768px)` block.

## Where each class is used

| Class | Used in |
|---|---|
| `.page`, `.page-header`, `.page-subtitle`, `.page-main`, `.top-frame-section`, `.bottom-frame-section`, `.action-column`, `.primary-button`, `.primary-button.secondary`, `.error-text` | [`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) |
| `.frame`, `.upload-frame`, `.image-container`, `.frame-image`, `.click-dot`, `.upload-placeholder`, `.upload-icon`, `.file-input` | [`UploadFrame.tsx`](../../react-front/src/components/widgets/UploadFrame.tsx) |
| `.frame`, `.result-frame`, `.frame-title`, `.frame-image`, `.frame-placeholder` | [`ResultFrame.tsx`](../../react-front/src/components/widgets/ResultFrame.tsx) |

## When to add styles

Add to the same file. Don't introduce CSS modules / Tailwind / etc. without a stronger reason than "more components" — the SPA is small enough that a single stylesheet remains tractable. If the file grows past a few hundred lines, the next sensible step is to split by component (one file per `.tsx`) before reaching for a framework.
