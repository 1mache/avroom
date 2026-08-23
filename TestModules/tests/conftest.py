from __future__ import annotations

import sys
from unittest.mock import MagicMock

sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())
sys.modules.setdefault("diffusers", MagicMock())


def pytest_configure(config: object) -> None:
    """Register custom markers used by network / Space tests."""
    config.addinivalue_line(  # type: ignore[attr-defined]
        "markers",
        "integration: needs network or external Hugging Face Spaces",
    )
