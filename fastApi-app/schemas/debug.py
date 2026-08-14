from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class DebugCheckResult(BaseModel):
    """One technical or content validation check's outcome, for the debug report."""

    name: Annotated[str, Field(description="Check identifier, e.g. 'blur' or 'exposure'.")]
    passed: Annotated[bool, Field(description="Whether this check passed.")]
    score: Annotated[
        float | None, Field(default=None, description="Check-specific numeric score, if any.")
    ]
    message: Annotated[
        str, Field(default="", description="Human-readable detail, populated mainly on failure.")
    ]


class DebugValidationResponse(BaseModel):
    """Full validation scoreboard for one uploaded image — technical + content checks.

    Unlike `POST /images/upload`, this never stops at the first failed check
    and never persists anything; it always returns 200 so a failed check reads
    as data, not an error.
    """

    ok: Annotated[bool, Field(description="True iff every technical and content check passed.")]
    technical_ok: Annotated[bool, Field(description="True iff every technical check passed.")]
    content_ok: Annotated[
        bool | None,
        Field(description="True/False if content validation ran; None if it was skipped."),
    ]
    technical: Annotated[
        list[DebugCheckResult], Field(description="Every technical check, in run order.")
    ]
    content: Annotated[
        list[DebugCheckResult],
        Field(default_factory=list, description="Every content (CLIP) check, if it ran."),
    ]
    content_skipped_reason: Annotated[
        str | None,
        Field(default=None, description="Why the content stage did not run, if it didn't."),
    ]
    elapsed_ms: Annotated[float, Field(description="Total wall time for both stages.")]
