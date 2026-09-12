import { useCallback, useState } from "react";

import { hasCloneSiblings } from "../types/session";
import type { CutoutObject } from "../types/session";

interface SessionObjects {
  objects: CutoutObject[];
  selectedObjectId: number | null;
  setSelectedObjectId: (objectId: number | null) => void;
  toggleHidden: (objectId: number) => void;
  revertRotation: (objectId: number) => Promise<void> | void;
  duplicateObject: (objectId: number) => Promise<void> | void;
  deleteObject: (objectId: number) => Promise<void>;
  clearObject3d: (objectId: number) => Promise<void> | void;
  resetObjectChanges: (objectId: number) => Promise<void> | void;
}

interface UseObjectActionsOptions {
  jobs: SessionObjects;
  /** The angle picker is scoped to one object; anything that disturbs that
   *  object has to close it. */
  cancelRotation: () => void;
  /** Selecting an object puts the toolbar back to its resting tool. */
  disarmTool: () => void;
  clearPendingSeeds: () => void;
  /** "Show original" bookkeeping, cleared when an object is reset. */
  forgetShowOriginal: (objectId: number) => void;
  onError: (message: string) => void;
}

/**
 * Everything the user can do to one object.
 *
 * Grouped because these all share two rules that were previously restated at
 * each call site: anything that disturbs the selected object closes the angle
 * picker, and anything needing a server round-trip refuses objects with no
 * uuid (rooms created before objects were given one).
 *
 * Delete is the exception that earns its extra state: an object with clone
 * siblings goes straight through, while the last of its lineage is held in
 * `pendingDeleteObject` until the user confirms.
 */
export function useObjectActions({
  jobs,
  cancelRotation,
  disarmTool,
  clearPendingSeeds,
  forgetShowOriginal,
  onError,
}: UseObjectActionsOptions) {
  const [pendingDeleteObjectId, setPendingDeleteObjectId] = useState<number | null>(null);

  /** Close the angle picker if this action touches the object it is open on. */
  const cancelRotationFor = useCallback(
    (objectId: number) => {
      if (jobs.selectedObjectId === objectId) {
        cancelRotation();
      }
    },
    [cancelRotation, jobs.selectedObjectId],
  );

  const selectObject = useCallback(
    (objectId: number | null) => {
      jobs.setSelectedObjectId(objectId);
      // Rotation is scoped to whichever object is selected — switching away
      // closes the angle picker.
      cancelRotation();
      disarmTool();
      clearPendingSeeds();
    },
    [cancelRotation, clearPendingSeeds, disarmTool, jobs.setSelectedObjectId],
  );

  const toggleHidden = useCallback(
    (objectId: number) => {
      cancelRotationFor(objectId);
      jobs.toggleHidden(objectId);
    },
    [cancelRotationFor, jobs.toggleHidden],
  );

  // "Show original" permanently drops the baked rotation (back to the
  // pristine cutout) rather than just previewing it -- a one-way revert,
  // not a toggle. jobs.revertRotation persists this via DELETE .../rotation.
  const toggleShowOriginal = useCallback(
    (objectId: number) => void jobs.revertRotation(objectId),
    [jobs.revertRotation],
  );

  const copySelected = useCallback(() => {
    const selectedId = jobs.selectedObjectId;
    if (selectedId === null) {
      return;
    }
    const target = jobs.objects.find((o) => o.objectId === selectedId);
    if (!target?.uuid) {
      onError("This object is from an older room and can't be duplicated.");
      return;
    }
    void jobs.duplicateObject(selectedId);
  }, [jobs.duplicateObject, jobs.objects, jobs.selectedObjectId, onError]);

  const requestDelete = useCallback(
    (objectId: number) => {
      const target = jobs.objects.find((o) => o.objectId === objectId);
      if (!target?.uuid) {
        onError("This object is from an older room and can't be deleted.");
        return;
      }
      cancelRotation();
      // One of several copies: losing it costs nothing that isn't recoverable
      // from a sibling, so skip the confirmation.
      if (hasCloneSiblings(target, jobs.objects)) {
        void jobs.deleteObject(objectId);
        return;
      }
      setPendingDeleteObjectId(objectId);
    },
    [cancelRotation, jobs.deleteObject, jobs.objects, onError],
  );

  const deleteSelected = useCallback(() => {
    if (jobs.selectedObjectId !== null) {
      requestDelete(jobs.selectedObjectId);
    }
  }, [jobs.selectedObjectId, requestDelete]);

  const clearObject3d = useCallback(
    (objectId: number) => {
      cancelRotationFor(objectId);
      void jobs.clearObject3d(objectId);
    },
    [cancelRotationFor, jobs.clearObject3d],
  );

  const resetChanges = useCallback(
    (objectId: number) => {
      cancelRotationFor(objectId);
      forgetShowOriginal(objectId);
      void jobs.resetObjectChanges(objectId);
    },
    [cancelRotationFor, forgetShowOriginal, jobs.resetObjectChanges],
  );

  const confirmDelete = useCallback(async () => {
    if (pendingDeleteObjectId === null) {
      return;
    }
    await jobs.deleteObject(pendingDeleteObjectId);
    setPendingDeleteObjectId(null);
  }, [jobs.deleteObject, pendingDeleteObjectId]);

  const cancelDelete = useCallback(() => setPendingDeleteObjectId(null), []);

  return {
    selectObject,
    toggleHidden,
    toggleShowOriginal,
    copySelected,
    requestDelete,
    deleteSelected,
    clearObject3d,
    resetChanges,
    pendingDeleteObject:
      jobs.objects.find((o) => o.objectId === pendingDeleteObjectId) ?? null,
    confirmDelete,
    cancelDelete,
  };
}
