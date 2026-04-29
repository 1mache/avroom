# Documentation layout (overview vs partials)

Each subsystem folder under `docs/ai-pipeline/` follows one rule:

- **`README.md`** — short overview only: what the subsystem is for, when it runs in the pipeline, one sentence on boundaries, and links into detail pages.
- **Partial pages** — specifics live here so READMEs stay skimmable:

| Partial | Typical contents |
|---------|------------------|
| `components.md` | Facades, strategies, helpers grouped by role |
| `flow.md` | Execution order and data moving stage to stage |
| `contracts.md` | Inputs, outputs, shapes, key dict keys |
| `operations.md` | Config knobs, env vars, caches, debug artifacts, failure boundaries |

Not every subsection needs all four files; omit a partial when it would duplicate another page or add no signal.

Upstream code roots remain [`TestModules/src/`](../../TestModules/src/).
