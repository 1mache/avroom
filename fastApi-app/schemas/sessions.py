from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from schemas.jobs import JobInfo


class SessionInfo(BaseModel):
    """Lightweight session descriptor returned by the sessions list endpoint."""

    uid: Annotated[str, Field(description="Session UID.")]
    name: Annotated[
        str | None,
        Field(default=None, description="Human-readable label set by the user, or None if unnamed."),
    ]
    last_changed: Annotated[
        str | None,
        Field(
            default=None,
            description="ISO-8601 UTC timestamp of the last client-visible session mutation, if any.",
        ),
    ]


class SessionSyncCheckRequest(BaseModel):
    """Request payload for checking whether a client session snapshot is still current."""

    client_last_changed: Annotated[
        str | None,
        Field(
            default=None,
            description="ISO-8601 UTC timestamp the client believes is current; null when unknown.",
        ),
    ]


class SessionSyncCheckResponse(BaseModel):
    """Result of comparing a client session timestamp against server truth."""

    last_changed: Annotated[
        str,
        Field(
            description=(
                "Server-side last-changed ISO-8601 UTC timestamp. Empty string when "
                "the session exists but has not been touched since this feature was added."
            ),
        ),
    ]
    needs_refresh: Annotated[
        bool,
        Field(description="True when the client must re-poll session data from the server."),
    ]
    jobs: Annotated[
        list[JobInfo],
        Field(
            default_factory=list,
            description="This session's non-done jobs plus unconsumed segment results, oldest first.",
        ),
    ]


class WarmSessionMapsResponse(BaseModel):
    """Result of warming depth/normal caches for the session's current canvas."""

    uid: Annotated[str, Field(description="Session UID.")]
    content_hash: Annotated[
        str,
        Field(description="SHA-256 hex of the canvas bytes used for cache keys."),
    ]
    depth_cache_hit: Annotated[
        bool,
        Field(description="True when the depth map was already on disk before this call."),
    ]
    normal_cache_hit: Annotated[
        bool | None,
        Field(
            default=None,
            description="True when normals were cached; null when NORMAL_MAP=false.",
        ),
    ]


class SessionPreviewRequest(BaseModel):
    """Request payload for POST /images/{uid}/preview.

    The frontend composites the inpainted background with every visible
    cutout at its current position onto an offscreen canvas and posts the
    result here, best-effort and debounced, so the dashboard can show each
    session as the user left it.
    """

    image_b64: Annotated[
        str,
        Field(min_length=1, description="Base64-encoded preview JPEG (no data: prefix)."),
    ]


class SetNameRequest(BaseModel):
    """Request payload for assigning a human-readable name to a session."""

    name: Annotated[str, Field(min_length=1, description="Desired session name.")]


class ImageUploadResponse(BaseModel):
    """Response returned after successfully uploading and storing an image.

    The `image_id` is what the frontend will use to reference this uploaded image.
    """

    image_id: Annotated[
        str,
        Field(description="Server-generated identifier for the stored image."),
    ]
    original_filename: Annotated[
        str | None,
        Field(
            default=None,
            description="Original filename sent by the client, if available.",
        ),
    ]
    stored_path: Annotated[
        str | None,
        Field(
            default=None,
            description="Absolute or relative filesystem path where the image is stored (for debugging).",
        ),
    ]
    last_changed: Annotated[
        str,
        Field(description="ISO-8601 UTC timestamp recorded when this session was created."),
    ]
