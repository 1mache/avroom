from __future__ import annotations

import sys


def test_ensure_mmcv_stub_registers_collect_env() -> None:
    """Stub must satisfy Metric3D's hard ``from mmcv.utils import collect_env``."""
    # Isolate from a real mmcv if present in the env.
    saved = {name: sys.modules.pop(name) for name in list(sys.modules) if name == "mmcv" or name.startswith("mmcv.")}

    try:
        from avroom_object_removal.ai_engines.normal_mapping.strategies.metric3d_normal_mapping_strategy import (
            _ensure_mmcv_stub,
        )

        _ensure_mmcv_stub()
        from mmcv.utils import collect_env

        info = collect_env()
        assert isinstance(info, dict)
        assert info.get("avroom_mmcv_stub") == "1"
    finally:
        for name in list(sys.modules):
            if name == "mmcv" or name.startswith("mmcv."):
                sys.modules.pop(name, None)
        sys.modules.update(saved)
