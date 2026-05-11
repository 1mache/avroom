"""Manual smoke test: load VFusion3D config and model from Hugging Face Hub.

Validates that ``AutoConfig`` / ``AutoModel`` can fetch
``jadechoghari/vfusion3d`` and execute its remote modeling code — the same
checkpoint used by :class:`Vfusion3dReconstructionStrategy`. First run
downloads weights; requires network and sufficient RAM/VRAM for your machine.

Run explicitly (not intended as automated CI). Usage from repo root::

    python TestModules/tests/test_vfusion3d_hub_load.py
"""

from __future__ import annotations

import logging

from transformers import AutoConfig, AutoModel

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_vfusion3d_hub_load")

MODEL_ID = "jadechoghari/vfusion3d"


def test_vfusion3d_hub_load() -> None:
    """Download/load Hub config and model (remote code). Breakpoint-friendly."""
    print("Downloading/Loading config...")
    config = AutoConfig.from_pretrained(MODEL_ID, trust_remote_code=True)
    print("Config loaded. Downloading/Loading model...")
    model = AutoModel.from_pretrained(MODEL_ID, trust_remote_code=True)
    print("Success!")
    logger.info(
        "Loaded: config=%s model=%s",
        type(config).__name__,
        type(model).__name__,
    )


if __name__ == "__main__":
    test_vfusion3d_hub_load()
