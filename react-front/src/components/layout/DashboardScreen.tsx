import React, { useCallback, useEffect, useState } from "react";

import {
  copySession,
  deleteSession,
  getActiveJobs,
  getSessions,
  setSessionName,
} from "../../api/images";
import type { JobInfo, SessionInfo } from "../../types/api";
import { byMostRecentlyEdited } from "../../utils/time";
import { SessionCard } from "../dashboard/SessionCard";
import { BackIcon, PlusIcon } from "../icons";
import { ConfirmDialog } from "../widgets/ConfirmDialog";

// How often the dashboard re-checks which sessions have queued/running or
// failed work while it's the visible screen -- cheap (one endpoint, all
// sessions in one call), so this runs unconditionally rather than gating on
// "is anything active" the way the workspace's per-session poll does.
const JOBS_POLL_INTERVAL_MS = 5000;

export interface DashboardScreenProps {
  projectId: string;
  projectName: string;
  onOpenSession: (uid: string) => void;
  onNewSession: () => void;
  onBack: () => void;
}

type LoadState = "loading" | "ready" | "offline";

/**
 * Rooms dashboard: one project's rooms — starting, reopening, renaming,
 * copying, deleting. Object editing lives in the workspace; project-level
 * actions live one screen up, in ProjectsScreen.
 */
export const DashboardScreen: React.FC<DashboardScreenProps> = ({
  projectId,
  projectName,
  onOpenSession,
  onNewSession,
  onBack,
}) => {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [pendingDeleteUid, setPendingDeleteUid] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [copyingUid, setCopyingUid] = useState<string | null>(null);
  const [renameTarget, setRenameTarget] = useState<SessionInfo | null>(null);
  const [renameName, setRenameName] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeJobs, setActiveJobs] = useState<JobInfo[]>([]);

  const load = useCallback(async () => {
    try {
      const list = await getSessions(projectId);
      setSessions([...list].sort(byMostRecentlyEdited));
      setLoadState("ready");
    } catch {
      setLoadState("offline");
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Session A can have a segment queued, session B an inpaint running — both
  // show it here without opening either. Failures (from a session nobody has
  // revisited to auto-dismiss) surface as a red dot the same way.
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const jobs = await getActiveJobs();
        if (!cancelled) {
          setActiveJobs(jobs);
        }
      } catch {
        // Non-fatal — next tick tries again.
      }
    };
    void poll();
    const interval = setInterval(() => void poll(), JOBS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const pendingDelete = sessions.find((s) => s.uid === pendingDeleteUid) ?? null;

  const handleConfirmDelete = useCallback(async () => {
    if (!pendingDeleteUid) {
      return;
    }

    setIsDeleting(true);
    try {
      await deleteSession(pendingDeleteUid);
      setSessions((prev) => prev.filter((s) => s.uid !== pendingDeleteUid));
      setPendingDeleteUid(null);
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : "Failed to delete the room.",
      );
    } finally {
      setIsDeleting(false);
    }
  }, [pendingDeleteUid]);

  const handleCopyRoom = useCallback(
    async (uid: string) => {
      setCopyingUid(uid);
      try {
        await copySession(uid);
        await load();
      } catch (copyError) {
        setError(copyError instanceof Error ? copyError.message : "Failed to copy the room.");
      } finally {
        setCopyingUid(null);
      }
    },
    [load],
  );

  const openRename = useCallback((uid: string) => {
    const session = sessions.find((s) => s.uid === uid) ?? null;
    if (!session) {
      return;
    }
    setRenameTarget(session);
    setRenameName(session.name ?? "");
  }, [sessions]);

  const handleRename = useCallback(async () => {
    const name = renameName.trim();
    if (!renameTarget || !name) {
      return;
    }
    setRenameBusy(true);
    try {
      const updated = await setSessionName(renameTarget.uid, name);
      setSessions((prev) =>
        [...prev.map((s) => (s.uid === updated.uid ? updated : s))].sort(byMostRecentlyEdited),
      );
      setRenameTarget(null);
    } catch (renameError) {
      setError(renameError instanceof Error ? renameError.message : "Failed to rename the room.");
    } finally {
      setRenameBusy(false);
    }
  }, [renameName, renameTarget]);

  return (
    <div className="dashboard">
      <header className="dash-header">
        <button type="button" className="tool-btn" onClick={onBack} aria-label="Back to projects" data-tip="Back to projects">
          <BackIcon />
        </button>
        <span className="dash-wordmark">{projectName}</span>
      </header>

      <main className="dash-main">
        <div className="new-session-row">
          <button type="button" className="new-session" onClick={onNewSession}>
            <span className="new-session-mark">
              <PlusIcon size={22} />
            </span>
            <span className="new-session-label">New room</span>
            <span className="new-session-hint">JPG, PNG or WebP · 640×480 and up</span>
          </button>
        </div>

        <div className="dash-eyebrow">
          <span className="dash-eyebrow-title">Rooms</span>
          {loadState === "ready" && sessions.length > 0 ? (
            <span className="dash-eyebrow-count">{String(sessions.length).padStart(2, "0")}</span>
          ) : null}
        </div>

        {/* Only the grid scrolls — starting a new session stays reachable no
            matter how far down the list you are. */}
        <div className="session-scroll">
          {loadState === "loading" ? (
            <div className="session-grid">
              <div className="session-skeleton" />
              <div className="session-skeleton" />
              <div className="session-skeleton" />
            </div>
          ) : loadState === "offline" ? (
            <div className="dash-note">
              <p className="dash-note-line">No answer from the image service</p>
              <button type="button" className="btn" onClick={() => void load()}>
                Try again
              </button>
            </div>
          ) : sessions.length === 0 ? (
            <div className="dash-note">
              <p className="dash-note-line">Nothing here yet</p>
              <p className="dash-note-hint">
                Start a room with a photo and it will show up here.
              </p>
            </div>
          ) : (
            <div className="session-grid">
              {sessions.map((session) => {
                const sessionJobs = activeJobs.filter((job) => job.session_id === session.uid);
                return (
                  <SessionCard
                    key={session.uid}
                    uid={session.uid}
                    name={session.name}
                    lastChanged={session.last_changed}
                    isBusy={sessionJobs.some((job) => job.status === "queued" || job.status === "running")}
                    isFailed={sessionJobs.some((job) => job.status === "failed" || job.status === "conflict")}
                    isCopying={copyingUid === session.uid}
                    onOpen={onOpenSession}
                    onRequestDelete={setPendingDeleteUid}
                    onRequestCopy={(uid) => void handleCopyRoom(uid)}
                    onRequestRename={openRename}
                  />
                );
              })}
            </div>
          )}
        </div>
      </main>

      {renameTarget ? (
        <ConfirmDialog
          title="Rename room"
          body={
            <input
              type="text"
              className="session-name"
              value={renameName}
              onChange={(event) => setRenameName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleRename();
              }}
              placeholder="Untitled room"
              autoFocus
            />
          }
          confirmLabel="Rename"
          busy={renameBusy}
          onConfirm={() => void handleRename()}
          onCancel={() => setRenameTarget(null)}
        />
      ) : null}

      {pendingDelete ? (
        <ConfirmDialog
          title="Delete this room?"
          body={
            <>
              <strong>{pendingDelete.name ?? "Untitled room"}</strong> and everything cut out of
              it will be removed. This can&rsquo;t be undone.
            </>
          }
          confirmLabel="Delete room"
          destructive
          busy={isDeleting}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setPendingDeleteUid(null)}
        />
      ) : null}

      {error ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setError(null)}>
          <div
            className="modal is-error"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="dash-error-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="dash-error-title">Request failed</h2>
              <button type="button" className="modal-close" onClick={() => setError(null)}>
                Close
              </button>
            </div>
            <pre className="modal-body">{error}</pre>
          </div>
        </div>
      ) : null}
    </div>
  );
};
