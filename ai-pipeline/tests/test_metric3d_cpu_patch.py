from __future__ import annotations

import types
from typing import Any
from unittest.mock import MagicMock, patch


def test_patch_metric3d_for_device_rewrites_get_bins() -> None:
    from avroom_object_removal.ai_engines.normal_mapping.strategies.metric3d_normal_mapping_strategy import (
        _patch_metric3d_for_device,
    )

    class _Decoder:
        min_val = 0.1
        max_val = 10.0

        def get_bins(self, bins_num: int) -> Any:
            raise AssertionError("original get_bins must be replaced")

    class _DepthModel:
        def __init__(self) -> None:
            self.decoder = _Decoder()

    class _HubModel:
        def __init__(self) -> None:
            self.depth_model = _DepthModel()

    model: Any = _HubModel()

    fake_torch = MagicMock()
    linspace_out = MagicMock(name="linspace_out")
    fake_torch.linspace.return_value = linspace_out
    fake_torch.exp.side_effect = lambda x: x

    with patch(
        "avroom_object_removal.ai_engines.normal_mapping.strategies.metric3d_normal_mapping_strategy.torch",
        fake_torch,
        create=True,
    ):
        # Patch imports torch inside the function — patch sys.modules instead.
        pass

    with patch.dict("sys.modules", {"torch": fake_torch}):
        _patch_metric3d_for_device(model, "cpu")
        assert isinstance(model.depth_model.decoder.get_bins, types.MethodType)
        model.depth_model.decoder.get_bins(4)

    assert fake_torch.linspace.call_args.kwargs.get("device") == "cpu"
