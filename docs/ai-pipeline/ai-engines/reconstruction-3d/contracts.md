# Reconstruction 3D contracts

- **Inputs:** Flexible image representations plus kwargs (`quality`, `output`, optional `seed`, optional HF token forwarding rules — see facade signature).
- **Outputs:** GLB binary blob or filesystem reference depending on `output` selector.

Contracts intentionally mirror standalone tooling usage — HTTP JSON responses do **not** yet expose GLB endpoints.
