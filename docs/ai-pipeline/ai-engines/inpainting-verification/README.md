# Inpainting verification

**What this is:** Post-inpaint quality check on a Stable Diffusion (or LaMa-only) candidate. The facade holds one `InpaintingVerificationStrategy`. Default is Gemini (`GEMINI_MODEL` from `.env`, fallback `gemini-2.5-flash-lite`). CLIP labels run when `GEMINI_API_KEY` is missing/placeholder or the call fails.

**When it runs:** Inside `HybridInpaintingStrategy.inpaint` after every candidate, including when SD is skipped. Singular `POST /images/inpaint` and batch peels both go through Hybrid, so both get this loop. There is no separate inference `JobKind`.

**In one line:** BGR candidate + mask + SD params in → `ok` plus JSON params to replay → Hybrid retries SD up to `INPAINT_VERIFY_MAX_RETRIES`.

Code: [`TestModules/src/ai_engines/inpainting_verification/`](../../../../TestModules/src/ai_engines/inpainting_verification/).

## Detail pages

- [components.md](components.md)
- [flow.md](flow.md)
- [contracts.md](contracts.md)
- [operations.md](operations.md)

Parent: [ai-engines/README.md](../README.md).
