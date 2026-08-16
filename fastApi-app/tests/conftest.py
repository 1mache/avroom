from __future__ import annotations

"""Shared pytest configuration for `fastApi-app/tests`.

Puts `fastApi-app/` on `sys.path` once, at collection time, so test modules
can `import core...` / `import api...` without each repeating its own
`sys.path` hack (several still do, harmlessly — this makes that redundant
rather than replacing them outright). Also the home for storage/DB fixtures
added as the AWS deployment prep work lands (see
docs/deployment/aws-runbook.md); none exist yet.
"""

import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))
