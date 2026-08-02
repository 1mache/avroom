import { useCallback, useState } from "react";

import { ApiError } from "../api/images";

export type ConflictContext = "segment" | "inpaint";

export interface ConflictNotice {
  id: number;
  context: ConflictContext;
  message: string;
}

const NOTICE_TTL_MS = 6000;

const isWriterTimeout = (detail: string): boolean => {
  const lower = detail.toLowerCase();
  return lower.includes("writer busy") || lower.includes("timeout");
};

const COPY: Record<ConflictContext, (detail: string) => string> = {
  segment: () => "That area is being removed right now — pick another spot.",
  inpaint: (detail) =>
    isWriterTimeout(detail)
      ? "Server is still busy with an earlier removal. Try again."
      : "Another removal is already running over that region.",
};

let noticeCounter = 0;

/**
 * 409s from segment/inpaint are expected traffic under the backend's new
 * region-lease concurrency (see docs/backend/concurrency.md), not failures —
 * they render as a dismissible, auto-expiring inline hint instead of opening
 * the modal error dialog. Anything else (wrong status, non-ApiError) is
 * rethrown so the caller's existing error-modal path handles it unchanged.
 */
export function useConflictNotices() {
  const [notices, setNotices] = useState<ConflictNotice[]>([]);

  const dismiss = useCallback((id: number) => {
    setNotices((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const notify = useCallback(
    (error: unknown, context: ConflictContext) => {
      if (!(error instanceof ApiError) || error.status !== 409) {
        throw error;
      }

      const id = ++noticeCounter;
      const message = COPY[context](error.detail);
      setNotices((prev) => [...prev, { id, context, message }]);
      setTimeout(() => dismiss(id), NOTICE_TTL_MS);
    },
    [dismiss],
  );

  return { notices, notify, dismiss };
}
