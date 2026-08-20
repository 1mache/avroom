from __future__ import annotations

import cv2
import numpy as np

from avroom_object_removal.ai_engines.mask_selection.scene_consensus_scoring import (
    alpha_from_cutout,
    area_biased_purity_score,
    boundary_edge_score,
    largest_iou_cluster,
    mask_area_fraction,
    purity_score,
)


def _bgra(*, alpha_rect: tuple[int, int, int, int]) -> np.ndarray:
    h = 100
    w = 100
    x0, y0, x1, y1 = alpha_rect
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[y0:y1, x0:x1, :3] = (40, 80, 120)
    out[y0:y1, x0:x1, 3] = 255
    return out


def test_boundary_edge_score_prefers_aligned_mask() -> None:
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(scene, (30, 30), (70, 70), (255, 255, 255), thickness=-1)

    tight = _bgra(alpha_rect=(30, 30, 70, 70))
    outlier = _bgra(alpha_rect=(20, 20, 80, 80))

    tight_score = boundary_edge_score(scene, alpha_from_cutout(tight))
    outlier_score = boundary_edge_score(scene, alpha_from_cutout(outlier))

    assert tight_score > outlier_score
    assert 0.0 <= tight_score <= 1.0
    assert 0.0 <= outlier_score <= 1.0


def test_largest_iou_cluster_keeps_largest_component() -> None:
    # 1,2,3 overlap strongly; 0 and 4 are isolated.
    cutouts = [
        _bgra(alpha_rect=(10, 10, 30, 30)),
        _bgra(alpha_rect=(30, 30, 70, 70)),
        _bgra(alpha_rect=(30, 30, 70, 70)),
        _bgra(alpha_rect=(30, 30, 70, 70)),
        _bgra(alpha_rect=(80, 80, 95, 95)),
    ]

    cluster = largest_iou_cluster(indices=(0, 1, 2, 3, 4), cutouts_bgra=cutouts, threshold=0.55)
    assert set(cluster) == {1, 2, 3}


def test_purity_score_uses_boundary_when_depth_missing() -> None:
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(scene, (30, 30), (70, 70), (255, 255, 255), thickness=-1)
    mask = _bgra(alpha_rect=(30, 30, 70, 70))

    score = purity_score(
        scene_bgr=scene,
        depth_map=None,
        mask_bool=alpha_from_cutout(mask),
        click_xy=(50, 50),
    )
    assert 0.0 <= score <= 1.0


def test_area_biased_purity_favors_larger_complete_mask() -> None:
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(scene, (30, 30), (70, 70), (255, 255, 255), thickness=-1)
    cv2.rectangle(scene, (35, 70), (40, 85), (255, 255, 255), thickness=-1)
    cv2.rectangle(scene, (60, 70), (65, 85), (255, 255, 255), thickness=-1)

    seat_only = _bgra(alpha_rect=(30, 30, 70, 70))
    with_legs = _bgra(alpha_rect=(30, 30, 70, 85))

    seat_purity = purity_score(
        scene_bgr=scene,
        depth_map=None,
        mask_bool=alpha_from_cutout(seat_only),
        click_xy=(50, 50),
    )
    full_purity = purity_score(
        scene_bgr=scene,
        depth_map=None,
        mask_bool=alpha_from_cutout(with_legs),
        click_xy=(50, 50),
    )
    assert seat_purity >= full_purity

    max_area = mask_area_fraction(alpha_from_cutout(with_legs))
    seat_score = area_biased_purity_score(
        purity=seat_purity,
        area_fraction=mask_area_fraction(alpha_from_cutout(seat_only)),
        max_area_fraction=max_area,
        area_exponent=1.0,
    )
    full_score = area_biased_purity_score(
        purity=full_purity,
        area_fraction=max_area,
        max_area_fraction=max_area,
        area_exponent=1.0,
    )
    assert full_score > seat_score

