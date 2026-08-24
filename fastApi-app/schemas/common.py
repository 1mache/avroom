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
    """Tight visible-object bounds inside the cutout image."""

    left: Annotated[int, Field(ge=0, description="Left-most visible pixel, inclusive.")]
    top: Annotated[int, Field(ge=0, description="Top-most visible pixel, inclusive.")]
    right: Annotated[int, Field(ge=0, description="Right-most visible bound, exclusive.")]
    bottom: Annotated[int, Field(ge=0, description="Bottom-most visible bound, exclusive.")]
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
