# Tests contracts

No frozen CLI interface — scripts mutate globals/tuples locally.

Expectations common across harnesses:

- Input imagery reachable via repo-relative paths baked into scripts (may require adjusting clones).
- Outputs assume writable working directories (`outputs/` folders).

Automated pytest harness absent — regression detection relies on developer comparing artifacts visually or archiving directories manually.
