"""Connect-only checks for Hugging Face Spaces used by 3D reconstruction.

Loads ``fastApi-app/.env`` for ``HUNYUAN3D_SPACE_ID``, ``TRELLIS_SPACE_ID``, and
``HF_TOKEN``. Opens a ``gradio_client.Client`` only — no ``generate`` / ``predict``.

Run from repo root (needs network)::

    python -m pytest TestModules/tests/test_hf_space_connect.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Keep defaults in sync with strategy DEFAULT_SPACE_ID values.
_DEFAULT_HUNYUAN = "es3d-fi/hunyuan3d-2-1"
_DEFAULT_TRELLIS = "microsoft/TRELLIS.2"

_ENV_PATH = Path(__file__).resolve().parents[2] / "fastApi-app" / ".env"


def _load_fastapi_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(_ENV_PATH)


def _hf_token() -> str | None:
    return os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN") or None


def _space_id(env_name: str, default: str) -> str:
    return os.environ.get(env_name, "").strip() or default


def _connect(space_id: str) -> object:
    from gradio_client import Client

    return Client(space_id, token=_hf_token())


@pytest.fixture(scope="module")
def fastapi_env() -> None:
    """Load Space ids / HF token from ``fastApi-app/.env`` once per module."""
    _load_fastapi_env()


@pytest.mark.integration
def test_connect_hunyuan3d_space(fastapi_env: None) -> None:
    space_id = _space_id("HUNYUAN3D_SPACE_ID", _DEFAULT_HUNYUAN)
    client = _connect(space_id)
    assert client is not None
    # Handshake succeeded; Space config is reachable without running generation.
    assert getattr(client, "config", None) is not None or hasattr(client, "predict")


@pytest.mark.integration
def test_connect_trellis_space(fastapi_env: None) -> None:
    space_id = _space_id("TRELLIS_SPACE_ID", _DEFAULT_TRELLIS)
    client = _connect(space_id)
    assert client is not None
    assert getattr(client, "config", None) is not None or hasattr(client, "predict")


@pytest.mark.integration
def test_space_ids_resolve_from_env(fastapi_env: None) -> None:
    """Env override wins; otherwise the code defaults match strategy constants."""
    hunyuan = _space_id("HUNYUAN3D_SPACE_ID", _DEFAULT_HUNYUAN)
    trellis = _space_id("TRELLIS_SPACE_ID", _DEFAULT_TRELLIS)
    assert "/" in hunyuan
    assert "/" in trellis
    # When .env sets the vars (as .env.example does), they must be non-empty.
    if _ENV_PATH.is_file():
        raw = _ENV_PATH.read_text(encoding="utf-8")
        if "HUNYUAN3D_SPACE_ID=" in raw:
            assert os.environ.get("HUNYUAN3D_SPACE_ID", "").strip() == hunyuan
        if "TRELLIS_SPACE_ID=" in raw:
            assert os.environ.get("TRELLIS_SPACE_ID", "").strip() == trellis
