import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE_URL, getSessionObjects, getUidCacheStatus, syncCheckSession } from "../api/images";
import { toCutoutAlphaBounds } from "./useSessionJobs";
import type { CutoutObject } from "../types/session";

const POLL_INTERVAL_MS = 2000;

interface UseSessionSyncOptions {
  imageId: string | null;
  /** Poll only while true — idle sessions never poll. */
  hasPendingWork: boolean;
  objects: CutoutObject[];
  setObjects: React.Dispatch<React.SetStateAction<CutoutObject[]>>;
  selectedObjectId: number | null;
  setSelectedObjectId: React.Dispatch<React.SetStateAction<number | null>>;
  setBackgroundSrc: React.Dispatch<React.SetStateAction<string | null>>;
}

/**
 * Detects session state changed elsewhere (another tab, another client) via
 * POST /images/{uid}/sync-check, and reconciles local object state against
 * server truth without clobbering purely-local fields (drag offset, hidden,
 * glbData, current selection).
 */
export function useSessionSync(options: UseSessionSyncOptions) {
  const {
    imageId,
    hasPendingWork,
    setObjects,
    setSelectedObjectId,
    setBackgroundSrc,
  } = options;

  const [lastChanged, setLastChangedState] = useState<string | null>(null);

  // Refs so interval/focus callbacks always see current values without
  // re-subscribing every render, and reconcile always merges against the
  // latest local objects/selection even though it's defined once.
  const imageIdRef = useRef(imageId);
  const lastChangedRef = useRef(lastChanged);
  const objectsRef = useRef(options.objects);
  const selectedObjectIdRef = useRef(options.selectedObjectId);

  useEffect(() => {
    imageIdRef.current = imageId;
  }, [imageId]);
  useEffect(() => {
    objectsRef.current = options.objects;
  }, [options.objects]);
  useEffect(() => {
    selectedObjectIdRef.current = options.selectedObjectId;
  }, [options.selectedObjectId]);

  const setLastChanged = useCallback((value: string | null) => {
    lastChangedRef.current = value;
    setLastChangedState(value);
  }, []);

  const reconcile = useCallback(
    async (uid: string, freshTimestamp: string) => {
      try {
        const [objList, cache] = await Promise.all([
          getSessionObjects(uid),
          getUidCacheStatus(uid),
        ]);

        const localById = new Map(objectsRef.current.map((o) => [o.objectId, o]));
        const serverIds = new Set(objList.objects.map((o) => o.object_id));

        const merged: CutoutObject[] = objList.objects.map((info) => {
          const local = localById.get(info.object_id);
          const cutoutSrc = `data:image/${info.format};base64,${info.cutout_b64}`;
          const cutoutAlphaBounds = toCutoutAlphaBounds(info.cutout_bounds);

          if (local) {
            // Update server-owned fields; keep purely-local/transient ones
            // (offset, hidden, glbData, normalizedClickPos) untouched.
            return {
              ...local,
              uuid: info.uuid ?? local.uuid,
              name: info.name ?? local.name,
              cutoutSrc,
              cutoutAlphaBounds: cutoutAlphaBounds ?? local.cutoutAlphaBounds,
            };
          }

          return {
            objectId: info.object_id,
            uuid: info.uuid ?? null,
            name: info.name ?? null,
            cutoutSrc,
            cutoutAlphaBounds,
            normalizedClickPos: null,
            glbData: null,
            hidden: false,
            offset: { x: 0, y: 0 },
          };
        });

        setObjects(merged);

        if (selectedObjectIdRef.current !== null && !serverIds.has(selectedObjectIdRef.current)) {
          setSelectedObjectId(null);
        }

        setBackgroundSrc(
          cache.has_background
            ? `${API_BASE_URL}/images/${uid}/background?t=${encodeURIComponent(freshTimestamp)}`
            : null,
        );
      } catch {
        // Non-fatal — next poll/focus tick tries again.
      }
    },
    [setObjects, setSelectedObjectId, setBackgroundSrc],
  );

  const checkNow = useCallback(async () => {
    const uid = imageIdRef.current;
    if (!uid) {
      return;
    }

    try {
      const result = await syncCheckSession(uid, lastChangedRef.current);
      setLastChanged(result.last_changed);
      if (result.needs_refresh) {
        await reconcile(uid, result.last_changed);
      }
    } catch {
      // Non-fatal — sync-check failures don't interrupt the session.
    }
  }, [reconcile, setLastChanged]);

  // Poll while there's in-flight work — another client/tab could commit in
  // the meantime. Idle sessions never poll.
  useEffect(() => {
    if (!imageId || !hasPendingWork) {
      return;
    }

    const interval = setInterval(checkNow, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [imageId, hasPendingWork, checkNow]);

  // Catch up once whenever the tab regains focus/visibility.
  useEffect(() => {
    if (!imageId) {
      return;
    }

    const handler = () => {
      if (document.visibilityState === "visible") {
        checkNow();
      }
    };

    window.addEventListener("focus", handler);
    document.addEventListener("visibilitychange", handler);
    return () => {
      window.removeEventListener("focus", handler);
      document.removeEventListener("visibilitychange", handler);
    };
  }, [imageId, checkNow]);

  return {
    lastChanged,
    seedLastChanged: setLastChanged,
    // Re-checks now; call after any local mutation and once right after a
    // session restore so lastChanged gets seeded without waiting for a poll
    // tick or focus event.
    recordLocalMutation: checkNow,
  };
}
