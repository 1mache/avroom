import React, { useCallback, useEffect, useState } from "react";

import { deleteSession, getSessions } from "../../api/images";
import avroomLogo from "../../assets/avroom.png";
import type { SessionInfo } from "../../types/api";
import { byMostRecentlyEdited } from "../../utils/time";
import { SessionCard } from "../dashboard/SessionCard";
import { FlaskIcon, PlusIcon } from "../icons";
import { ConfirmDialog } from "../widgets/ConfirmDialog";

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
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [pendingDeleteUid, setPendingDeleteUid] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        <button
          type="button"
          className="tool-btn dash-header-end"
          onClick={onOpenDebug}
          aria-label="Pipeline debug"
          data-tip="Pipeline debug"
        >
          <FlaskIcon />
        </button>
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
              {sessions.map((session) => (
                <SessionCard
                  key={session.uid}
                  uid={session.uid}
                  name={session.name}
                  lastChanged={session.last_changed}
                  onOpen={onOpenSession}
                  onRequestDelete={setPendingDeleteUid}
                />
              ))}
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
