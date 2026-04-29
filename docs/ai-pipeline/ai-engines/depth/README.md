# Depth

**What this is:** Builds one grayscale depth map per frame so segmentation and routing can reason about geometry instead of RGB texture.

**When it runs:** First ML stage inside `remove_object`, immediately after decode.

**In one line:** Two Depth Anything variants blended so walls and foreground stay coherent without harsh seams.

Code: [`TestModules/src/ai_engines/depth/`](../../../../TestModules/src/ai_engines/depth/).

## Detail pages

- [components.md](components.md) — facade and strategies
- [flow.md](flow.md) — near/far blend steps
- [contracts.md](contracts.md) — input/output arrays
- [operations.md](operations.md) — model ids, caching, cost

Parent: [ai-engines/README.md](../README.md).
