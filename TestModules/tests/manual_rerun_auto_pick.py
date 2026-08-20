"""Manual smoke check: rerun auto mask selection offline on saved candidates.

Loads the six cutouts dumped by the last failing debug run plus the original
photo (found by sha256), then calls select_best_cutout with the real Gemini
key from fastApi-app/.env. Not a pytest test — run directly.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "TestModules" / "outputs" / "auto_mask_pick"
ORIGINAL = REPO / "fastApi-app" / "tmp" / "images" / "058f79db-c453-4751-8da0-196cb67a5516.jpeg"
CLICK = (100, 728)


def _env(name: str) -> str | None:
    text = (REPO / "fastApi-app" / ".env").read_text(encoding="utf-8")
    m = re.search(rf'^{name}\s*=\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
    return m.group(1).strip() if m else None


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else _env("GEMINI_MODEL")
    api_key = _env("GEMINI_API_KEY")
    assert api_key, "no key in .env"

    from avroom_object_removal import select_best_cutout
    from avroom_object_removal.ai_engines.mask_selection.strategies import (
        GeminiCutoutAllCandidatesTiebreakStrategy,
    )

    cutouts = []
    masks = []
    for i in range(6):
        img = cv2.imread(str(OUT / f"{i:02d}_cutout.png"), cv2.IMREAD_UNCHANGED)
        assert img is not None and img.shape[2] == 4, f"bad cutout {i}"
        cutouts.append(img)
        masks.append((img[:, :, 3] > 0).astype(np.uint8) * 255)

    scene = cv2.imread(str(ORIGINAL), cv2.IMREAD_COLOR)
    assert scene is not None

    result = select_best_cutout(
        cutouts,
        click_xy=CLICK,
        refined_masks=masks,
        scene_bgr=scene,
        depth_map=None,
        scorer=None,
        tiebreaker=GeminiCutoutAllCandidatesTiebreakStrategy(
            api_key=api_key, model_id=model
        ),
    )
    print(f"model={model}")
    print(f"winner={result.winner_index} finalists={result.finalist_indices}")
    print(f"method={result.tiebreak_method}")
    print(f"reason={result.tiebreak_reason}")
    print(f"reasons={result.reasons}")


if __name__ == "__main__":
    main()
