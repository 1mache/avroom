from __future__ import annotations

import sys
from unittest.mock import MagicMock

sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())
sys.modules.setdefault("diffusers", MagicMock())
