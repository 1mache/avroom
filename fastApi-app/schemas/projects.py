from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class ProjectInfo(BaseModel):
    """One project, with fields derived from its rooms for the dashboard card."""

    id: Annotated[str, Field(description="Project id.")]
    name: Annotated[str, Field(description="Human-readable project name.")]
    room_count: Annotated[int, Field(description="Number of rooms (sessions) in this project.")]
    last_changed: Annotated[
        str | None,
        Field(
            default=None,
            description="ISO-8601 UTC timestamp of the most recently edited room, if any.",
        ),
    ]
    preview_uid: Annotated[
        str | None,
        Field(
            default=None,
            description="Room uid whose preview thumbnail represents this project, if any.",
        ),
    ]


class CreateProjectRequest(BaseModel):
    """Request payload for POST /projects."""

    name: Annotated[str, Field(min_length=1, max_length=255, description="Desired project name.")]


class SetProjectNameRequest(BaseModel):
    """Request payload for POST /projects/{project_id}/name."""

    name: Annotated[str, Field(min_length=1, max_length=255, description="Desired project name.")]
