from __future__ import annotations

from typing import Sequence

from ..mask_selection_strategy import (
    MaskSelectionContext,
    MaskSelectionStrategy,
    ScoredCandidate,
)
from ..scene_consensus_scoring import (
    alpha_from_cutout,
    area_biased_purity_score,
    largest_iou_cluster,
    mask_area_fraction,
    purity_score,
)

# ponytail: exponent trades completeness vs leak; raise if fragments still win.
_AREA_EXPONENT = 1.0


class SceneConsensusMaskSelectionStrategy(MaskSelectionStrategy):
    """Recommended selection policy for auto-pick.

    Scoring uses *scene purity* (boundary alignment) and optional depth
    coherence. Masks are grouped by alpha-IoU similarity; only the largest
    consensus cluster is eligible to win. Ranking (and area bias) applies
    inside that cluster; outliers are tagged ``consensus_outlier``.
    """

    def needs_clip(self) -> bool:
        return False

    def rank_scores(
        self, candidates: Sequence[ScoredCandidate], ctx: MaskSelectionContext
    ) -> dict[int, float]:
        indices = [c.index for c in candidates]
        cluster = set(
            largest_iou_cluster(indices=indices, cutouts_bgra=ctx.cutouts_bgra)
        )

        purities: dict[int, float] = {}
        areas: dict[int, float] = {}
        for cand in candidates:
            cutout_bgra = ctx.cutouts_bgra[cand.index]
            mask_bool = alpha_from_cutout(cutout_bgra)
            areas[cand.index] = mask_area_fraction(mask_bool)
            if ctx.scene_bgr is None and ctx.depth_map is None:
                purities[cand.index] = 0.0
                continue
            purities[cand.index] = purity_score(
                scene_bgr=ctx.scene_bgr,
                depth_map=ctx.depth_map,
                mask_bool=mask_bool,
                click_xy=ctx.click_xy,
                click_xys=ctx.click_xys or (ctx.click_xy,),
            )

        cluster_areas = [areas[index] for index in cluster]
        max_area = max(cluster_areas, default=0.0)
        ranked: dict[int, float] = {}
        for index, purity in purities.items():
            if index not in cluster:
                ranked[index] = purity
                continue
            ranked[index] = area_biased_purity_score(
                purity=purity,
                area_fraction=areas[index],
                max_area_fraction=max_area,
                area_exponent=_AREA_EXPONENT,
            )
        return ranked

    def eligible_indices(
        self, candidates: Sequence[ScoredCandidate], ctx: MaskSelectionContext
    ) -> tuple[int, ...]:
        if not candidates:
            return ()
        indices = [c.index for c in candidates]
        return largest_iou_cluster(
            indices=indices,
            cutouts_bgra=ctx.cutouts_bgra,
        )

    def reason_for(
        self,
        index: int,
        *,
        eligible: bool,
        clip_checks: dict[str, float] | None = None,
    ) -> str:
        del index, clip_checks
        return "consensus_ranked" if eligible else "consensus_outlier"
