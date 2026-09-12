from __future__ import annotations

import numpy as np

from avroom_object_removal.utils import colorize_normals, normals_from_vis_bgr


def test_colorize_normals_roundtrip_unit_vectors() -> None:
    """8-bit encode/decode recovers axes within quantization error."""
    h, w = 4, 5
    normals = np.zeros((h, w, 3), dtype=np.float32)
    normals[:, :, 0] = 1.0  # +X
    normals[1, 1] = (0.0, 1.0, 0.0)
    normals[2, 2] = (0.0, 0.0, 1.0)
    normals[3, 3] = (-1.0 / np.sqrt(2), 0.0, 1.0 / np.sqrt(2))

    norms = np.linalg.norm(normals, axis=2, keepdims=True)
    normals = normals / np.maximum(norms, 1e-8)

    bgr = colorize_normals(normals)
    assert bgr.dtype == np.uint8
    assert bgr.shape == (h, w, 3)

    recovered = normals_from_vis_bgr(bgr)
    rec_norms = np.linalg.norm(recovered, axis=2, keepdims=True)
    recovered = recovered / np.maximum(rec_norms, 1e-8)

    assert np.allclose(recovered[0, 0], normals[0, 0], atol=0.02)
    assert np.allclose(recovered[1, 1], normals[1, 1], atol=0.02)
    assert np.allclose(recovered[2, 2], normals[2, 2], atol=0.02)
    assert np.allclose(recovered[3, 3], normals[3, 3], atol=0.03)


def test_colorize_normals_rejects_bad_shape() -> None:
    try:
        colorize_normals(np.zeros((4, 5), dtype=np.float32))
    except ValueError:
        return
    raise AssertionError("expected ValueError for HxW input")
