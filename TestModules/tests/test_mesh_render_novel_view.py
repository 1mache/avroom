"""Unit tests for MeshRenderNovelViewStrategy."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

trimesh = pytest.importorskip("trimesh")

from avroom_object_removal.ai_engines.novel_view.strategies.mesh_render_novel_view_strategy import (  # noqa: E402
    MeshRenderNovelViewError,
    MeshRenderNovelViewStrategy,
    _cartesian_from_spherical,
    _orbit_camera_position,
    _spherical_from_cartesian,
)


def _make_cutout_rgba(size: int = 64) -> Image.Image:
    """Opaque centered square on a transparent canvas."""

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inset = size // 4
    for y in range(inset, size - inset):
        for x in range(inset, size - inset):
            canvas.putpixel((x, y), (200, 80, 40, 255))
    return canvas


def _box_glb_bytes() -> bytes:
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    # Solid color so textured/untextured paths both have faces to draw.
    mesh.visual.face_colors = [180, 120, 60, 255]
    data = mesh.export(file_type="glb")
    assert isinstance(data, (bytes, bytearray))
    return bytes(data)


class TestOrbitCameraMath:
    def test_roundtrip_spherical(self) -> None:
        eye = np.array([0.0, 1.5, 7.0], dtype=np.float64)
        az, polar, radius = _spherical_from_cartesian(eye)
        rebuilt = _cartesian_from_spherical(az, polar, radius)
        assert np.allclose(eye, rebuilt, atol=1e-6)

    def test_zero_deltas_match_start(self) -> None:
        eye = _orbit_camera_position(
            azimuth_deg=0.0,
            relative_elevation_deg=0.0,
            radius=0.0,
        )
        assert np.allclose(eye, np.array([0.0, 1.5, 7.0]), atol=1e-5)

    def test_positive_radius_moves_farther(self) -> None:
        near = _orbit_camera_position(azimuth_deg=0.0, relative_elevation_deg=0.0, radius=0.0)
        far = _orbit_camera_position(azimuth_deg=0.0, relative_elevation_deg=0.0, radius=0.5)
        assert np.linalg.norm(far) > np.linalg.norm(near)


def _pyrender_available() -> bool:
    try:
        import pyrender

        renderer = pyrender.OffscreenRenderer(viewport_width=8, viewport_height=8)
        renderer.delete()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _pyrender_available(), reason="pyrender/OpenGL offscreen unavailable")
class TestMeshRenderNovelViewStrategy:
    def test_synthesize_returns_bgra_matching_canvas(self) -> None:
        cutout = _make_cutout_rgba(64)
        strategy = MeshRenderNovelViewStrategy(render_size=128)
        result = strategy.synthesize(
            cutout,
            elevation_deg=15.0,
            azimuth_deg=40.0,
            relative_elevation_deg=10.0,
            radius=0.0,
            mesh=_box_glb_bytes(),
        )
        assert result.dtype == np.uint8
        assert result.shape == (64, 64, 4)
        assert int(result[:, :, 3].max()) > 0

    def test_missing_mesh_without_reconstruction_raises(self) -> None:
        strategy = MeshRenderNovelViewStrategy()
        with pytest.raises(MeshRenderNovelViewError, match="mesh="):
            strategy.synthesize(
                _make_cutout_rgba(32),
                elevation_deg=0.0,
                azimuth_deg=0.0,
            )

    def test_mesh_path_loads(self, tmp_path: Path) -> None:
        glb_path = tmp_path / "box.glb"
        glb_path.write_bytes(_box_glb_bytes())
        strategy = MeshRenderNovelViewStrategy(render_size=64)
        result = strategy.synthesize(
            _make_cutout_rgba(32),
            elevation_deg=0.0,
            azimuth_deg=-30.0,
            mesh=glb_path,
        )
        assert result.shape == (32, 32, 4)
        assert int(result[:, :, 3].sum()) > 0


def test_empty_mesh_bytes_raise() -> None:
    strategy = MeshRenderNovelViewStrategy()
    with pytest.raises(MeshRenderNovelViewError, match="empty"):
        strategy.synthesize(
            _make_cutout_rgba(16),
            elevation_deg=0.0,
            azimuth_deg=0.0,
            mesh=b"",
        )
