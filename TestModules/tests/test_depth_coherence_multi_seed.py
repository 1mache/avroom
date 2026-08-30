from __future__ import annotations

import numpy as np

from avroom_object_removal.ai_engines.mask_selection.scene_consensus_scoring import (
    depth_coherence_score,
)


def test_depth_coherence_accepts_bimodal_mask_with_two_seed_depths() -> None:
    depth = np.zeros((100, 100), dtype=np.uint8)
    depth[10:40, 10:40] = 80
    depth[60:90, 60:90] = 200

    mask = np.zeros((100, 100), dtype=bool)
    mask[10:40, 10:40] = True
    mask[60:90, 60:90] = True

    score = depth_coherence_score(
        depth,
        mask,
        click_xy=(20, 20),
        click_xys=((20, 20), (70, 70)),
        tol=0.15,
    )

    assert score == 1.0
