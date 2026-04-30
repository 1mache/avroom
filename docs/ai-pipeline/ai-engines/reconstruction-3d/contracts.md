# Reconstruction 3D contracts

- **Inputs:** Flexible image representations accepted by `to_pil_rgba`, plus keyword args on `generate`: `quality`, `output`, optional `output_path`, `seed`. Additional behavior (for example HF token use) is defined by the **active concrete strategy**, not by the facade’s public surface.
- **Outputs:** GLB binary blob, filesystem path, or file-like handle depending on the `output` selector (`bytes` | `path` | `file`).

Contracts intentionally mirror standalone tooling usage — HTTP JSON responses do **not** yet expose GLB endpoints.
