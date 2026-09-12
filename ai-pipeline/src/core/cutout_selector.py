from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

import cv2
import numpy as np
from PIL import Image

from ..ai_engines.mask_selection.clip_cutout_checks import (
    CHECK_PASS_THRESHOLD,
    CLIP_CUTOUT_CHECKS,
    LabelScorer,
    average_positive_score,
    score_cutout_checks,
)
from ..ai_engines.mask_selection.mask_selection_strategy import (
    MaskSelectionContext,
    MaskSelectionStrategy,
    ScoredCandidate,
)
from ..ai_engines.mask_selection.mask_selection_tiebreak_strategy import (
    MaskSelectionTiebreakStrategy,
    TiebreakRequest,
)
from ..ai_engines.mask_selection.strategies import SceneConsensusMaskSelectionStrategy
from ..utils.debug_image_saver import DebugImageSaver

logger = logging.getLogger(__name__)

_DEBUG_FOLDER = "outputs/auto_mask_pick"

DEFAULT_THRESHOLD = 0.6
MIN_AREA_FRACTION = 0.003
MAX_AREA_FRACTION = 0.70
TIE_BAND = 0.03
_GRAY = 128


@dataclass(frozen=True)
class CutoutSelectionResult:
    """Outcome of ranking BGRA cutout candidates for one click.

    ``scores`` holds the mean CLIP check score per candidate (0.0 when rejected).
    ``reasons`` is one tag per cutout (``click_miss``, ``clip_fail:complete``,
    ``scored``, ``winner``, …).
    """

    winner_index: int | None
    scores: tuple[float, ...]
    reasons: tuple[str, ...]
    average_scores: tuple[float, ...] = ()
    clip_checks: tuple[dict[str, float] | None, ...] = ()
    finalist_indices: tuple[int, ...] = ()
    tiebreak_method: Literal["none", "gemini", "clip_fallback"] = "none"
    tiebreak_reason: str | None = None


def select_best_cutout(
    cutouts_bgra: Sequence[np.ndarray],
    *,
    click_xy: tuple[int, int],
    click_xys: Sequence[tuple[int, int]] | None = None,
    scorer: LabelScorer | None = None,
    refined_masks: Sequence[np.ndarray] | None = None,
    scene_bgr: np.ndarray | None = None,
    depth_map: np.ndarray | None = None,
    tiebreaker: MaskSelectionTiebreakStrategy | None = None,
    selection_strategy: MaskSelectionStrategy | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> CutoutSelectionResult:
    """Pick the best complete-object cutout for ``click_xy``, or none.

    Each viable candidate gets CLIP check scores. A pluggable
    ``selection_strategy`` decides which scored candidates are eligible to
    compete for winner/tie-break resolution. When top scores cluster within
    ``TIE_BAND``, an optional ``tiebreaker`` (Gemini) chooses among finalists.

    ``threshold`` is retained for API compatibility; gating uses per-check
    thresholds in :mod:`clip_cutout_checks`.
    """
    del threshold

    policy = selection_strategy or SceneConsensusMaskSelectionStrategy()
    normalized_clicks = tuple(click_xys) if click_xys else (click_xy,)

    ctx = MaskSelectionContext(
        cutouts_bgra=cutouts_bgra,
        click_xy=click_xy,
        scene_bgr=scene_bgr,
        depth_map=depth_map,
        click_xys=normalized_clicks,
    )
    needs_clip = policy.needs_clip()

    n = len(cutouts_bgra)
    scores: list[float] = [0.0] * n
    reasons: list[str] = ["unknown"] * n
    clip_checks: list[dict[str, float] | None] = [None] * n
    clip_crops_bgr: list[np.ndarray | None] = [None] * n

    if needs_clip and scorer is None:
        raise ValueError("scorer is required when selection_strategy.needs_clip() is True")

    scored_candidates: list[ScoredCandidate] = []
    for index, cutout in enumerate(cutouts_bgra):
        reason = _prefilter_reason(cutout, normalized_clicks)
        if reason is not None:
            reasons[index] = reason
            _log_candidate(index, passed=False, avg=0.0, checks=None, reason=reason)
            continue

        crop = _crop_on_gray(cutout)
        if crop is None:
            reasons[index] = "empty_crop"
            _log_candidate(index, passed=False, avg=0.0, checks=None, reason="empty_crop")
            continue

        clip_crops_bgr[index] = _pil_rgb_to_bgr(crop)

        avg = 0.0
        check_scores: dict[str, float] | None = None
        if needs_clip:
            assert scorer is not None
            check_scores = score_cutout_checks(scorer, crop)
            clip_checks[index] = check_scores
            avg = average_positive_score(check_scores)
            scores[index] = avg

        scored_candidates.append(
            ScoredCandidate(
                index=index,
                avg_score=avg,
                clip_checks=check_scores or {},
                clip_crop_bgr=clip_crops_bgr[index],
            )
        )

    winner_index: int | None = None
    finalist_indices: tuple[int, ...] = ()
    tiebreak_method: Literal["none", "gemini", "clip_fallback"] = "none"
    tiebreak_reason: str | None = None

    rank_scores = policy.rank_scores(scored_candidates, ctx)
    for cand in scored_candidates:
        scores[cand.index] = float(rank_scores.get(cand.index, 0.0))

    eligible_indices = policy.eligible_indices(scored_candidates, ctx)
    eligible_set = set(eligible_indices)

    # Now that we know eligibility, log PASS/FAIL for each scored candidate.
    for candidate in scored_candidates:
        eligible = candidate.index in eligible_set
        reasons[candidate.index] = policy.reason_for(
            candidate.index,
            eligible=eligible,
            clip_checks=(candidate.clip_checks if needs_clip else None),
        )
        _log_candidate(
            candidate.index,
            passed=eligible,
            avg=scores[candidate.index],
            checks=(candidate.clip_checks if needs_clip else None),
            reason=reasons[candidate.index],
        )

    if eligible_indices:
        eligible_sorted = sorted(
            eligible_indices, key=lambda index: scores[index], reverse=True
        )
        send_all_to_gemini = (
            tiebreaker is not None
            and getattr(tiebreaker, "select_all_candidates", False) is True
        )
        if send_all_to_gemini:
            finalists = list(eligible_sorted)
        else:
            top_avg = scores[eligible_sorted[0]]
            finalists = [
                index for index in eligible_sorted if scores[index] >= top_avg - TIE_BAND
            ]
        finalist_indices = tuple(finalists)

        if len(finalists) == 1:
            winner_index = finalists[0]
        elif tiebreaker is not None and scene_bgr is not None:
            crops_bgr = {
                index: clip_crops_bgr[index]
                for index in finalists
                if clip_crops_bgr[index] is not None
            }
            refined_map: dict[int, np.ndarray] | None = None
            if refined_masks is not None:
                refined_map = {
                    index: refined_masks[index]
                    for index in finalists
                    if index < len(refined_masks)
                }
            tiebreak = tiebreaker.pick_among(
                TiebreakRequest(
                    scene_bgr=scene_bgr,
                    click_xy=click_xy,
                    click_xys=normalized_clicks,
                    finalist_indices=tuple(finalists),
                    cutout_crops_bgr=crops_bgr,
                    clip_averages={index: scores[index] for index in finalists},
                    refined_masks=refined_map,
                )
            )
            winner_index = tiebreak.candidate_index
            tiebreak_method = tiebreak.method
            tiebreak_reason = tiebreak.reason
        else:
            winner_index = finalists[0]
            tiebreak_method = "clip_fallback"
            tiebreak_reason = "no tiebreaker or scene"

    if winner_index is not None:
        reasons[winner_index] = "winner"

    logger.info(
        "Cutout selection finished: winner=%s scores=%s finalists=%s tiebreak=%s",
        winner_index,
        tuple(round(score, 3) for score in scores),
        finalist_indices,
        tiebreak_method,
    )

    result = CutoutSelectionResult(
        winner_index=winner_index,
        scores=tuple(scores),
        reasons=tuple(reasons),
        average_scores=tuple(scores),
        clip_checks=tuple(clip_checks),
        finalist_indices=finalist_indices,
        tiebreak_method=tiebreak_method,
        tiebreak_reason=tiebreak_reason,
    )
    try:
        _save_auto_mask_debug(
            cutouts_bgra,
            click_xy=click_xy,
            click_xys=normalized_clicks,
            result=result,
            reasons=tuple(reasons),
            clip_crops_bgr=clip_crops_bgr,
            clip_checks=tuple(clip_checks),
        )
    except OSError as exc:
        # Debug artifacts are best-effort; concurrent runs share the folder
        # and Windows locks files being written/read.
        logger.warning("Auto mask pick debug save skipped: %s", exc)
    return result


def _prefilter_reason(
    cutout_bgra: np.ndarray,
    click_xys: Sequence[tuple[int, int]],
) -> str | None:
    """Return a reject reason, or None if the cutout may be scored."""
    if cutout_bgra.ndim != 3 or cutout_bgra.shape[2] < 4:
        return "invalid_cutout"

    height, width = cutout_bgra.shape[:2]
    for click_x, click_y in click_xys:
        if click_x < 0 or click_y < 0 or click_x >= width or click_y >= height:
            return "click_miss"
        if cutout_bgra[click_y, click_x, 3] == 0:
            return "click_miss"

    alpha = cutout_bgra[:, :, 3] > 0
    area_fraction = float(np.count_nonzero(alpha)) / float(height * width)
    if area_fraction < MIN_AREA_FRACTION:
        return "area_too_small"
    if area_fraction > MAX_AREA_FRACTION:
        return "area_too_large"
    return None


def _format_clip_checks(check_scores: dict[str, float] | None) -> str:
    """Compact per-check score and pass/fail for logs."""
    if not check_scores:
        return "-"
    parts: list[str] = []
    for check in CLIP_CUTOUT_CHECKS:
        value = check_scores.get(check.key)
        if value is None:
            parts.append(f"{check.key}=missing")
            continue
        verdict = "pass" if value >= CHECK_PASS_THRESHOLD else "fail"
        parts.append(f"{check.key}={value:.3f}:{verdict}")
    return " ".join(parts)


def _log_candidate(
    index: int,
    *,
    passed: bool,
    avg: float,
    checks: dict[str, float] | None,
    reason: str,
) -> None:
    """INFO line per SAM candidate: CLIP average, each check, pass/fail."""
    logger.info(
        "Cutout candidate %d: %s avg=%.3f checks=[%s] reason=%s",
        index,
        "PASS" if passed else "FAIL",
        avg,
        _format_clip_checks(checks),
        reason,
    )


def _crop_on_gray(cutout_bgra: np.ndarray) -> Image.Image | None:
    alpha = cutout_bgra[:, :, 3]
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not rows.any() or not cols.any():
        return None

    y0, y1 = np.where(rows)[0][[0, -1]]
    x0, x1 = np.where(cols)[0][[0, -1]]
    crop = cutout_bgra[y0 : y1 + 1, x0 : x1 + 1]
    rgb = cv2.cvtColor(crop[:, :, :3], cv2.COLOR_BGR2RGB)
    alpha_f = crop[:, :, 3].astype(np.float32) / 255.0
    gray = np.full_like(rgb, _GRAY, dtype=np.float32)
    blended = (
        rgb.astype(np.float32) * alpha_f[..., None] + gray * (1.0 - alpha_f[..., None])
    ).astype(np.uint8)
    return Image.fromarray(blended)


def _pil_rgb_to_bgr(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _cutout_preview_bgr(
    cutout_bgra: np.ndarray,
    click_xys: Sequence[tuple[int, int]],
) -> np.ndarray:
    bgr = cutout_bgra[:, :, :3].copy()
    visible = cutout_bgra[:, :, 3] > 0
    bgr[~visible] = 0
    for click_x, click_y in click_xys:
        cv2.circle(bgr, (click_x, click_y), 6, (0, 0, 255), 2)
    return bgr


def _save_auto_mask_debug(
    cutouts_bgra: Sequence[np.ndarray],
    *,
    click_xy: tuple[int, int],
    click_xys: Sequence[tuple[int, int]],
    result: CutoutSelectionResult,
    reasons: tuple[str, ...],
    clip_crops_bgr: Sequence[np.ndarray | None],
    clip_checks: tuple[dict[str, float] | None, ...],
) -> None:
    """Write candidates, CLIP crops, winner, and score JSON under outputs/auto_mask_pick."""
    saver = DebugImageSaver(output_folder_name=_DEBUG_FOLDER)
    output_dir = Path(saver.output_dir)
    for stale in output_dir.iterdir():
        if stale.is_file():
            try:
                stale.unlink()
            except OSError:
                pass  # locked by a concurrent run or viewer; overwrite later

    candidates_meta: list[dict[str, float | int | str | dict[str, float] | None]] = []
    for index, cutout in enumerate(cutouts_bgra):
        score = result.scores[index] if index < len(result.scores) else 0.0
        reason = reasons[index] if index < len(reasons) else "unknown"
        checks = clip_checks[index] if index < len(clip_checks) else None
        saver.save(f"{index:02d}_cutout", cutout)
        if cutout.ndim == 3 and cutout.shape[2] >= 4:
            saver.save(f"{index:02d}_alpha", cutout[:, :, 3])
            saver.save(f"{index:02d}_preview", _cutout_preview_bgr(cutout, click_xys))
        crop_bgr = clip_crops_bgr[index] if index < len(clip_crops_bgr) else None
        if crop_bgr is not None:
            saver.save(f"{index:02d}_clip_crop", crop_bgr)
        candidates_meta.append(
            {
                "index": index,
                "score": round(float(score), 4),
                "reason": reason,
                "clip_checks": checks,
            }
        )

    if result.winner_index is not None and 0 <= result.winner_index < len(cutouts_bgra):
        saver.save("winner", cutouts_bgra[result.winner_index])

    summary = {
        "click_xy": [click_xy[0], click_xy[1]],
        "click_xys": [[point[0], point[1]] for point in click_xys],
        "winner_index": result.winner_index,
        "finalist_indices": list(result.finalist_indices),
        "tiebreak_method": result.tiebreak_method,
        "tiebreak_reason": result.tiebreak_reason,
        "candidates": candidates_meta,
    }
    summary_path = output_dir / "selection.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Auto mask pick debug saved: %s", output_dir)
