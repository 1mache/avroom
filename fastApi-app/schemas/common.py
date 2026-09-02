from __future__ import annotations

"""Schema types and constants shared across the other `schemas/` modules.

`CutoutBounds` is needed by `schemas/jobs.py` (for `SegmentMaskResult`) and
every module that describes an object or cutout (`schemas/image.py`,
`schemas/objects.py`, `schemas/novel_view.py`). `VerifyMode` straddles the
legacy click/segment schema and the batch schema; `DEFAULT_SOURCE_ELEVATION_DEG`
straddles the object schema and the novel-view endpoint. Keeping all of them
here, rather than in whichever feature module happened to define them first,
is what lets `schemas/sessions.py` import `schemas/jobs.py` (for `JobInfo`,
to embed each session's jobs on `SessionSyncCheckResponse`) without a cycle.
"""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class CutoutBounds(BaseModel):
    """Object bounds in natural-image pixels.

    Usually the tight alpha box inside a cutout/rotation PNG (edges inside the
    frame). Placement responses may also return *logical* bounds after
    ``display_scale`` growth, which can extend past the canvas (negative
    left/top or right/bottom beyond natural size) so clients see overflow.
    """

    left: Annotated[int, Field(description="Left-most visible edge, inclusive (may be < 0 when scaled).")]
    top: Annotated[int, Field(description="Top-most visible edge, inclusive (may be < 0 when scaled).")]
    right: Annotated[int, Field(description="Right-most visible edge, exclusive (may exceed natural_width).")]
    bottom: Annotated[int, Field(description="Bottom-most visible edge, exclusive (may exceed natural_height).")]
    natural_width: Annotated[int, Field(gt=0, description="Full cutout image width in pixels.")]
    natural_height: Annotated[int, Field(gt=0, description="Full cutout image height in pixels.")]


# Fallback source elevation used whenever an object predates elevation
# estimation or its metadata could not be read. Kept here (rather than in
# schemas/objects.py or schemas/novel_view.py) so the object schema, the
# stored metadata model (core/object_metadata.py), and the novel-view
# endpoint -- which straddle both -- cannot drift apart.
DEFAULT_SOURCE_ELEVATION_DEG = 15.0


class VerifyMode(str, Enum):
    """Whether the client or CLIP selects among SAM cutout candidates.

    Shared between the legacy click/segment schemas and the batch schema,
    which is why it lives here rather than in either of those modules.
    """

    MANUAL = "manual"
    AUTO = "auto"
