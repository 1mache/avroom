from __future__ import annotations

"""Schema types shared across `schemas/image.py` and `schemas/jobs.py`.

Pulled out so `schemas/jobs.py` (which `schemas/image.py`'s
`SessionSyncCheckResponse` needs, to embed each session's jobs) doesn't have
to import back from `schemas/image.py` and create a cycle.
"""

from typing import Annotated

from pydantic import BaseModel, Field


class CutoutBounds(BaseModel):
    """Tight visible-object bounds inside the cutout image."""

    left: Annotated[int, Field(ge=0, description="Left-most visible pixel, inclusive.")]
    top: Annotated[int, Field(ge=0, description="Top-most visible pixel, inclusive.")]
    right: Annotated[int, Field(ge=0, description="Right-most visible bound, exclusive.")]
    bottom: Annotated[int, Field(ge=0, description="Bottom-most visible bound, exclusive.")]
    natural_width: Annotated[int, Field(gt=0, description="Full cutout image width in pixels.")]
    natural_height: Annotated[int, Field(gt=0, description="Full cutout image height in pixels.")]
