from __future__ import annotations

import cv2
import numpy as np

from avroom_object_removal import select_best_cutout


def _bgra(*, alpha_rect: tuple[int, int, int, int] | None) -> np.ndarray:
    """Build a BGRA cutout. ``alpha_rect`` uses exclusive coords."""
    h = 100
    w = 100
    out = np.zeros((h, w, 4), dtype=np.uint8)
    if alpha_rect is None:
        return out
    x0, y0, x1, y1 = alpha_rect
    out[y0:y1, x0:x1, :3] = (40, 80, 120)
    out[y0:y1, x0:x1, 3] = 255
    return out


def test_scene_consensus_picks_tight_largest_cluster() -> None:
    # Scene edges exist only for the tight rectangle.
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(scene, (30, 30), (70, 70), (255, 255, 255), thickness=-1)

    # Candidate 0 is an outlier (larger mask).
    # Candidates 1-4 are identical tight masks.
    # Candidate 5 is a small fragment.
    cutouts = [
        _bgra(alpha_rect=(20, 20, 80, 80)),  # 0 outlier
        _bgra(alpha_rect=(30, 30, 70, 70)),  # 1 tight
        _bgra(alpha_rect=(30, 30, 70, 70)),  # 2 tight
        _bgra(alpha_rect=(30, 30, 70, 70)),  # 3 tight
        _bgra(alpha_rect=(30, 30, 70, 70)),  # 4 tight
        _bgra(alpha_rect=(40, 40, 60, 60)),  # 5 fragment
    ]

    # No scorer: scene consensus skips CLIP entirely.
    result = select_best_cutout(
        cutouts,
        click_xy=(50, 50),
        scene_bgr=scene,
        depth_map=None,
        scorer=None,
    )

    assert result.winner_index == 1
    assert result.reasons[1] == "winner"
    assert result.reasons[0] == "consensus_outlier"
    assert result.reasons[5] == "consensus_outlier"
    assert all(
        result.reasons[i] == "consensus_ranked" for i in (2, 3, 4)
    )


def test_scene_consensus_prefers_full_chair_over_seat_only() -> None:
    scene = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(scene, (30, 30), (70, 70), (255, 255, 255), thickness=-1)
    cv2.rectangle(scene, (35, 70), (40, 85), (255, 255, 255), thickness=-1)
    cv2.rectangle(scene, (60, 70), (65, 85), (255, 255, 255), thickness=-1)

    cutouts = [
        _bgra(alpha_rect=(10, 10, 25, 25)),  # 0 outlier
        _bgra(alpha_rect=(30, 30, 70, 70)),  # 1 seat-only sibling
        _bgra(alpha_rect=(30, 30, 70, 70)),  # 2 seat-only sibling
        _bgra(alpha_rect=(30, 30, 70, 85)),  # 3 full chair with legs
        _bgra(alpha_rect=(30, 30, 70, 70)),  # 4 seat-only sibling
        _bgra(alpha_rect=(30, 30, 70, 70)),  # 5 seat-only sibling
    ]

    result = select_best_cutout(
        cutouts,
        click_xy=(50, 50),
        scene_bgr=scene,
        depth_map=None,
        scorer=None,
    )

    assert result.winner_index == 3
    assert result.reasons[3] == "winner"

