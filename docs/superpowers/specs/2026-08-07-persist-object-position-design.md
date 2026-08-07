# Persist object position (drag offset)

## Context

Every `CutoutObject` has an `offset` (natural-image pixels) that positions its cutout on top of the background. Today this lives only in React state — `useSessionJobs.updateOffset` never calls the backend, and `loadRestoredObjects` hardcodes `offset: { x: 0, y: 0 }` for every object it restores. Dragging an object, then leaving and reopening the session (or just reloading the tab), silently discards the move.

This was surfaced while chasing dashboard-preview bugs in the same session: the preview thumbnail now correctly reflects a drag ~0.5s after it happens, which made the *position itself* not surviving a reload much more visible and confusing (thumbnail shows the new spot, workspace doesn't).

This spec covers persisting that offset server-side, and, since duplicating an object already copies its source's offset locally, extends that copy to be a real (nudged) position computed and stored atomically at clone time.

## Storage

`ObjectMetadata` (`fastApi-app/core/object_metadata.py`) gains two fields:

```python
offset_x: Annotated[float, Field(default=0.0, description="Drag offset from center, natural-image pixels.")]
offset_y: Annotated[float, Field(default=0.0, description="Drag offset from center, natural-image pixels.")]
```

Defaulted so every existing `_meta.json` on disk (written before this change) still deserializes cleanly as `(0.0, 0.0)` — no migration needed.

New helper, mirroring `set_object_average_depth` (`object_metadata.py:201-213`):

```python
def set_object_offset(base_dir: Path, object_uuid: str, offset_x: float, offset_y: float) -> ObjectMetadata:
    """Update the persisted drag offset on an existing object metadata record."""
```

Load by uuid, `model_copy(update={...})`, write, `logger.info`, return. Raises `FileNotFoundError` on unknown uuid, same as its sibling.

## Endpoint: generalize `PATCH /images/objects/{uuid}`

`SetObjectNameRequest` (`schemas/image.py:269`) is renamed `UpdateObjectRequest` and gains two optional fields:

```python
class UpdateObjectRequest(BaseModel):
    """Partial update for one object: name and/or drag offset."""

    name: Annotated[str | None, Field(default=None, description="New object name, or null to clear. Omit the field entirely to leave the name unchanged.")]
    offset_x: Annotated[float | None, Field(default=None, description="New drag offset X (natural-image px). Omit to leave unchanged.")]
    offset_y: Annotated[float | None, Field(default=None, description="New drag offset Y (natural-image px). Omit to leave unchanged.")]
```

**The gotcha this spec exists to call out explicitly:** `name`'s `None` means "clear the name" (existing behavior, unchanged), but `offset_x`/`offset_y`'s `None` means "not included in this request" — a drag-persist call never mentions `name`, a rename call never mentions offset. Because Pydantic can't tell "omitted from JSON" from "explicitly `None`" using field defaults alone, the handler must inspect `UpdateObjectRequest.model_fields_set` (the set of field names actually present in the parsed request body) to decide what to touch:

```python
@router.patch("/objects/{object_uuid}", response_model=ObjectMetadataResponse)
async def update_object(object_uuid: str, request: UpdateObjectRequest) -> ObjectMetadataResponse:
    storage_dir = get_image_storage_dir()
    metadata = get_object_by_uuid(storage_dir, object_uuid)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Object not found for uuid='{object_uuid}'")

    fields = request.model_fields_set
    if "name" in fields:
        metadata = set_object_name(storage_dir, object_uuid, request.name)
    if "offset_x" in fields or "offset_y" in fields:
        metadata = set_object_offset(
            storage_dir,
            object_uuid,
            request.offset_x if request.offset_x is not None else metadata.offset_x,
            request.offset_y if request.offset_y is not None else metadata.offset_y,
        )
    touch_session(metadata.session_id)
    return _metadata_to_response(metadata, storage_dir, get_3d_storage_dir())
```

(Route function renamed from `rename_object` to `update_object` to match its new scope.) No canvas-writer lock — single metadata-file write, same as today's rename.

`ObjectMetadataResponse` (`schemas/image.py:332`) and `ObjectInfo` (`schemas/image.py:365`) both gain `offset_x: float` / `offset_y: float` (required, not optional, in the response — the stored value always exists once `ObjectMetadata` has the defaulted fields).

## Frontend: API wrapper and types

`react-front/src/api/images.ts`: rename the `setObjectName` request type usage to match the renamed schema conceptually (TS side can keep `setObjectName(uuid, name)` as a thin wrapper posting `{ name }`, since it's still a common call site), and add:

```ts
export async function setObjectOffset(objectUuid: string, x: number, y: number): Promise<ObjectMetadataResponse> {
  // PATCH /images/objects/${objectUuid} with { offset_x: x, offset_y: y }
}
```

`types/api.ts`: `ObjectInfo` and `ObjectMetadataResponse` gain `offset_x: number`, `offset_y: number`.

## Frontend: restore

`useSessionJobs.loadRestoredObjects` (`:148`) stops hardcoding `offset: { x: 0, y: 0 }`:

```ts
offset: { x: info.offset_x ?? 0, y: info.offset_y ?? 0 },
```

(`??` fallback covers any object metadata written before this change that somehow lacks the field at the JSON level — belt-and-braces alongside the Pydantic default.)

## Frontend: persist on drag-end

`WorkspaceScreen.tsx`'s `finishDrag` (`:752`) already has the final offset by the time it clears `dragStateRef` (every intermediate position went through `jobs.updateOffset`, which only touches local state). After the existing cleanup:

```ts
const dragged = jobs.objects.find((o) => o.objectId === dragStateRef.current /* captured before clearing */ ?.objectId);
if (dragged?.uuid) {
  void setObjectOffset(dragged.uuid, dragged.offset.x, dragged.offset.y).catch((err) => {
    console.warn("setObjectOffset failed; position won't survive reload.", err);
  });
}
```

No-op for legacy objects without a `uuid` (same precondition as duplicate/delete). Detached, not awaited by the caller, no busy/spinner state — a missed save on one drag isn't worth interrupting the user, and the next drag's PATCH will overwrite it with the latest position anyway. Failure is `console.warn`-logged rather than silently swallowed, following the pattern already fixed for the preview pipeline this session — so a broken persist path doesn't go unnoticed again.

## Backend: duplicate computes and stores the nudge atomically

No new endpoint, no frontend follow-up call. `build_clone_metadata` (`core/object_metadata.py`, called from `duplicate_object` in `routes.py:653+`) computes the clone's `offset_x`/`offset_y` as part of building the metadata it already returns — same request, same `save_object_metadata` write.

It needs the source object's canvas width and alpha bounds. Both come from decoding the source cutout PNG (already resolved and read via `resolve_object_cutout_path` earlier in `duplicate_object`) with the existing `extract_cutout_bounds_from_png_bytes` (`core/cutout_bounds.py`) — cutouts are full-canvas-sized transparent PNGs, so the decoded image's own dimensions are the canvas size, no separate background lookup needed.

Nudge algorithm (ported from the client-side `clampCutoutOffset` math, `stageGeometry.ts:117-142`):

```python
def _nudge_clone_offset(
    source_offset_x: float, bounds: CutoutBounds, canvas_width: int,
) -> float:
    """Try nudging left by ~15% of the object's own width; fall back to right, then no nudge."""
    width = bounds.right - bounds.left
    nudge = max(12.0, width * 0.15)

    min_x = -bounds.left
    max_x = canvas_width - bounds.right

    left_candidate = source_offset_x - nudge
    if left_candidate >= min_x:
        return left_candidate

    right_candidate = source_offset_x + nudge
    if right_candidate <= max_x:
        return right_candidate

    return source_offset_x  # no room either side; clone lands exactly on the source
```

`offset_y` is always copied unchanged from the source (horizontal nudge only, matching common duplicate-nudge UX). If bounds can't be extracted (extremely degenerate cutout), fall back to `offset_x = source_offset_x` — never fail the duplicate over this.

The frontend's `duplicateObject` (`useSessionJobs.ts:389-448`) needs no changes beyond consuming the now-present `offset_x`/`offset_y` fields on the `getSessionObjects` response it already fetches — replace its current `offset: { ...source.offset }` (client-computed copy) with `offset: { x: info.offset_x, y: info.offset_y }` (server-computed nudge).

## Error handling

- Unknown uuid on `PATCH /images/objects/{uuid}` → 404, unchanged from today.
- `duplicate_object`'s existing error handling (404 on missing source/cutout, 409 on writer-lock timeout, 500 + rollback on unexpected failure) is untouched; the nudge computation happens inside the same try block as the rest of clone-metadata construction, so a nudge failure is covered by the existing rollback path.
- Drag-persist failures never surface to the user — logged only, matching the just-fixed preview-save pattern.

## Testing

Backend (`fastApi-app/tests/`):
- `test_object_update.py` (new, or extend an existing object test file): PATCH with only `offset_x`/`offset_y` leaves `name` untouched; PATCH with only `name` leaves offset untouched; PATCH with both updates both; unknown uuid → 404; `touch_session` bumped.
- `test_object_duplicate.py`: extend with a case asserting the clone's `offset_x` is nudged left of the source by roughly the expected amount when there's room, and nudged right when the source already sits at the left edge (`bounds.left == 0`, `offset_x == -bounds_left_edge`... i.e. construct a source whose `min_x` is already reached).

Frontend: `npm run build` (tsc) for type coverage; no existing frontend test runner to extend.

Manual end-to-end (same seeding approach used earlier this session — real upload + directly-seeded cutout/meta, since full segment/inpaint needs GPU-backed models):
1. Drag an object, wait a beat, reload the page (or close/reopen the session) — object is where you left it.
2. Duplicate an object — clone appears nudged left of the source (or right, if the source is flush against the left edge); reload — clone stays in its nudged spot.
3. Rename an object right after dragging it (or vice versa) — confirm neither operation clobbers the other's stored value.

## Out of scope

- Vertical nudging (horizontal only).
- Retry-on-failure for the drag-persist PATCH.
- Migrating/backfilling `offset_x`/`offset_y` for objects that existed before this change (they simply default to `(0, 0)`, i.e. today's behavior, until next dragged).
- Any change to `rescale-by-depth` (scales the cutout in place; unrelated to position).
