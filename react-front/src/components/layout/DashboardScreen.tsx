import React, { useCallback, useEffect, useState } from "react";

import { deleteSession, getActiveJobs, getSessions } from "../../api/images";
import avroomLogo from "../../assets/avroom.png";
import { useAuth } from "../../context/AuthContext";
import type { JobInfo, SessionInfo } from "../../types/api";
import { byMostRecentlyEdited } from "../../utils/time";
import { SessionCard } from "../dashboard/SessionCard";
import { FlaskIcon, LogoutIcon, PlusIcon } from "../icons";
import { ConfirmDialog } from "../widgets/ConfirmDialog";

// How often the dashboard re-checks which sessions have queued/running or
// failed work while it's the visible screen -- cheap (one endpoint, all
// sessions in one call), so this runs unconditionally rather than gating on
// "is anything active" the way the workspace's per-session poll does.
const JOBS_POLL_INTERVAL_MS = 5000;

export interface DashboardScreenProps {
  onOpenSession: (uid: string) => void;
  onNewSession: () => void;
  onOpenDebug: () => void;
}

type LoadState = "loading" | "ready" | "offline";

/**
 * Home screen: everything that owns a session as a whole — starting one,
 * reopening one, deleting one. Editing lives in the workspace.
 */
export const DashboardScreen: React.FC<DashboardScreenProps> = ({
  onOpenSession,
  onNewSession,
  onOpenDebug,
}) => {
  const { user, logout } = useAuth();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [pendingDeleteUid, setPendingDeleteUid] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeJobs, setActiveJobs] = useState<JobInfo[]>([]);

  const load = useCallback(async () => {
    try {
      const list = await getSessions();
      setSessions([...list].sort(byMostRecentlyEdited));
      setLoadState("ready");
    } catch {
      setLoadState("offline");
    }
  }, []);

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
        deleteError instanceof Error ? deleteError.message : "Failed to delete the session.",
      );
    } finally {
      setIsDeleting(false);
    }
  }, [pendingDeleteUid]);

  return (
    <div className="dashboard">
      <header className="dash-header">
        <img src={avroomLogo} alt="" className="dash-logo" />
        <span className="dash-wordmark">AVRoom</span>
        <div className="dash-header-end">
          {user?.is_admin && (
            <button
              type="button"
              className="tool-btn"
              onClick={onOpenDebug}
              aria-label="Pipeline debug"
              data-tip="Pipeline debug"
            >
              <FlaskIcon />
            </button>
          )}
          <button type="button" className="tool-btn" onClick={logout} aria-label="Sign out" data-tip="Sign out">
            <LogoutIcon />
          </button>
        </div>
      </header>

      <main className="dash-main">
        <button type="button" className="new-session" onClick={onNewSession}>
          <span className="new-session-mark">
            <PlusIcon size={22} />
          </span>
          <span className="new-session-label">New session</span>
          <span className="new-session-hint">JPG, PNG or WebP · 640×480 and up</span>
        </button>

        <div className="dash-eyebrow">
          <span className="dash-eyebrow-title">Past sessions</span>
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
                Start a session with a room photo and it will show up here.
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
                    onOpen={onOpenSession}
                    onRequestDelete={setPendingDeleteUid}
                  />
                );
              })}
            </div>
          )}
        </div>
      </main>

      {pendingDelete ? (
        <ConfirmDialog
          title="Delete this session?"
          body={
            <>
              <strong>{pendingDelete.name ?? "Untitled session"}</strong> and everything cut out of
              it will be removed. This can&rsquo;t be undone.
            </>
          }
          confirmLabel="Delete session"
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
