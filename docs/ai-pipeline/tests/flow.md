# Tests execution flow

Typical developer workflow:

1. Configure image paths / coordinate tuples directly inside chosen script (many constants remain inline).
2. Run script via `python TestModules/tests/<script>.py` from repo root or package virtualenv.
3. Inspect emitted PNG/GLB artifacts under `TestModules/outputs/` or script-specific archives (`script_test_outputs/` subtree when runner copies results).

Smoke scripts exit nonzero when inference surfaces fatal exceptions — no standardized assertions beyond runtime prints.
