# Midterm Presentation Plan — AVRoom

Per guidelines: **not** 8–10 dense text slides. ~**4–5 content slides** carry the story; **the**
rest are **code/log/UI screenshots** that prove it's real. Bullets only, no walls of text.
Talk over the screenshots — don't read them.

Target deck size: **~10 slides total** = 5 content + 5 screenshot/demo.

Each slide below lists: **what to say** + **what to show** (exact file/lines to screenshot).

---

## SLIDE 1 — Title + the problem (content)

- Project name: **AVRoom (Adaptive Virtual Room)** — AI interior-design workspace.
- One-line pitch: upload room photo → click furniture → it's removed, background inpainted,
  and the cutout can become a 3D model.
- Team names, course, date.
- Links footer (required by guidelines): GitHub repo, Idea doc, HLD doc.

**Show:** clean title slide + one hero before/after image (room with sofa → room without sofa).

---

## SLIDE 2 — What's actually built vs. the vision (content)

- Honest scope. Guidelines reward truth over over-claiming.
- **Done today:** multi-object interactive removal (click → mask candidates → pick → inpaint,
  removals stack), per-object 3D generation behind a test endpoint.
- **Planned, not built:** Java/Spring core, Postgres+S3, auth, collaboration (OT roles),
  drag-and-drop, NLP edits. (from CLAUDE.md "Planned but Not Yet Implemented")
- Frame: MVP proves the hard part (the AI pipeline); the rest is conventional plumbing.

**Show:** simple 2-column "Done / Planned" table. No screenshot needed.

---

## SLIDE 3 — Architecture, 3 tiers (content)

- React SPA → FastAPI (the IPE / Image Processing Engine) → `avroom_object_removal` Python
  package, imported **in-process** (no IPC).
- Mention the HTTP contract: `/images/upload`, `/segment`, `/inpaint`, `/3d/test-3d`.

**Show:** screenshot the mermaid component diagram from
[architecture.md](architecture.md#L7-L21) (lines 7–21). Render it first so it's a clean graphic,
not raw markdown.

---

## SLIDE 4 — The AI pipeline, and the one trick that matters (content)

- 7 stages: Depth → Adapt → Route → Segment (SAM) → Refine → Inpaint → Compose.
- The non-obvious decisions (this is the "engineering insight" judges look for):
  - **SAM receives the depth map, not RGB** — RGB over-segments on fabric creases/shadows.
  - **Near-far depth blend is alpha compositing, not averaging** — prevents wall seams.
  - **Dilate mask before LaMa** — tight masks make LaMa bleed object pixels (halo).
- These are the "Rules Never to Break" from CLAUDE.md — good talking points.

**Show:** the pipeline stage list as a horizontal flow graphic (7 boxes). Keep text tiny;
narrate the 3 rules.

---

## SLIDE 5 — Swappable 3D reconstruction (content) ⭐ the one you asked for

- Image-to-GLB is a **Strategy pattern**: one ABC, 5 interchangeable backends.
- Backends today: **TripoSR** (local, fast fallback), **OpenLRM** (local), **Trellis 2**
  (HF Space), **VFusion3D**, **Hunyuan3D-2** (current default).
- Facade holds one primary + one fallback; if primary throws, fallback runs automatically.
- Swapping = change one constructor arg. No call-site changes. That's the whole point.
- Why it matters: 3D model quality/latency landscape moves fast — we A/B backends without
  touching the API or frontend.

**Show:** see the dedicated screenshot slides 5a–5c below. This content slide is the "why";
the screenshots are the "proof".

---

## SCREENSHOT SLIDES (code + logs)

### SLIDE 5a — The Strategy contract (screenshot)

- File: [reconstruction_3d_strategy.py](ai-pipeline/../../TestModules/src/ai_engines/reconstruction_3d/reconstruction_3d_strategy.py)
- Screenshot lines **16–41**: the `Reconstruction3DStrategy` ABC — one `generate()` method,
  same signature for every backend. This is what makes them interchangeable.
- Caption: "Every 3D backend implements this. Nothing else."

### SLIDE 5b — Swapping backends in one line (screenshot)

- File: `TestModules/src/ai_engines/reconstruction_3d/reconstruction_3d_facade.py`
- Screenshot lines **30–36** (the `__init__`): default = `Hunyuan3D2ReconstructionStrategy()`,
  fallback = `TriposrReconstructionStrategy()`.
- Screenshot lines **57–85** (the `generate` try/fallback) — primary fails → fallback runs →
  if both fail, one `RuntimeError`.
- Also screenshot `strategies/__init__.py` lines **3–35** — the 5 registered strategies +
  their error types, all exported side by side. This is the visual "menu of backends".
- Caption: "Pick a backend = one constructor arg. Built-in automatic fallback."

### SLIDE 5c — A concrete backend: Trellis 2 over a HF Space (screenshot)

- File: `TestModules/src/ai_engines/reconstruction_3d/strategies/trellis_reconstruction_strategy.py`
- Screenshot the `_call_space` method, lines **154–241**: two-step Space API
  (`/image_to_3d` → `/extract_glb`), lazy client, error wrapping.
- Optional second crop: `reconstruction_quality.py` **PRESETS** table (lines 46–65) — FAST /
  BALANCED / HIGH map to resolution + sampling steps + decimation + texture size.
- Caption: "Local backends (TripoSR/OpenLRM) and remote (Trellis Space) behind the same ABC."

### SLIDE 6 — Backend endpoint wiring (screenshot)

- File: `fastApi-app/api/routes.py` — screenshot the `/segment` (line 246) and `/inpaint`
  (line 298) decorators + function signatures (just the headers + docstrings, not full bodies).
- Optionally `fastApi-app/api/model_3d.py` `POST /3d/test-3d` handler.
- Caption: "Thin FastAPI layer; real work is the in-process pipeline call."

### SLIDE 7 — Live execution logs (screenshot) ⭐ proves it runs

- Run one full request, then screenshot `fastApi-app/logs/app.log`.
- Pick the lines showing the **pipeline stages firing in order**: depth → route (`run_context`,
  expand px, is_3d) → SAM → refine → inpaint, with the `INFO` stage timings.
- For 3D: screenshot the `Reconstruction3DFacade ready (strategy=..., fallback=...)` line and a
  `generate complete: quality=... glb_bytes=...` line.
- Caption: "Structured logs at every stage (LOG_LEVEL-controlled), not print()."
- **To produce these logs:** start server `cd fastApi-app; uvicorn main:app --reload`, do one
  upload→click→inpaint from the UI, then grab `logs/app.log`.

### SLIDE 8 — The working UI (screenshot, 2–3 shots) ⭐ the demo proof

- Real frontend screenshots, in sequence:
  1. Upload + image loaded, click point on an object.
  2. Mask candidates shown, one selected.
  3. Result: background inpainted + cutout in the `ObjectPanel` rail. Bonus: a generated 3D GLB.
- Caption: "End-to-end, multi-object, removals stack."
- **To produce:** `cd react-front; npm run dev` against the running FastAPI.

---

## SLIDE 9 — AI usage in our workflow (content)

- Guidelines explicitly ask how the team used AI tools.
- Be concrete: code generation, docs generation (the `docs/` tree + `update-docs` skill),
  testing strategy, model selection for the 3D backends.
- Mention what AI did **not** decide — the architecture rules (SAM-on-depth, alpha blend,
  dilation) were our engineering calls, validated by experiment.

**Show:** short bullet list. No screenshot.

---

## SLIDE 10 — Roadmap + the demo site (content / close)

- Next milestones from "Planned but Not Yet Implemented": auth + persistence, drag-and-drop
  repositioning, NLP edits, wiring 3D into the main flow.
- Restate required links (also keep them clickable on the live demo page):
  - GitHub repo
  - Idea / spec doc (`SpecDocument1.1.pdf`)
  - HLD doc
- Close on the before/after hero image again.

---

## Quick checklist before presenting

- [ ] Render the mermaid diagram to an image (don't screenshot raw markdown).
- [ ] Generate fresh `app.log` from one real run for Slide 7.
- [ ] Capture 3 UI screenshots for Slide 8 from a live session.
- [ ] Confirm GitHub + Idea + HLD links are live on the demo page (guideline requirement).
- [ ] Keep slides to bullets; rehearse narration over the code/log shots.
- [ ] 10-minute talk + 5-minute Q&A — budget ~1 min/slide.
```
