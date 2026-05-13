import React, { useEffect, useState } from "react";
import { getSessions, getUidCacheStatus } from "../../api/images";

interface SessionMeta {
  uid: string;
  hasResults: boolean;
}

interface SessionPickerProps {
  onSessionSelect: (uid: string) => void;
}

export const SessionPicker: React.FC<SessionPickerProps> = ({ onSessionSelect }) => {
  const [sessions, setSessions] = useState<SessionMeta[] | null>(null);

  useEffect(() => {
    let cancelled = false;

    getSessions()
      .then(async (uids) => {
        if (cancelled) return;
        // Fetch cache status for each uid in parallel to show result indicators
        const metas = await Promise.all(
          uids.map(async (uid): Promise<SessionMeta> => {
            try {
              const status = await getUidCacheStatus(uid);
              return { uid, hasResults: status.has_background || status.has_cutout };
            } catch {
              return { uid, hasResults: false };
            }
          }),
        );
        if (!cancelled) setSessions(metas);
      })
      .catch(() => {
        if (!cancelled) setSessions([]);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="session-picker">
      <span className="session-picker-label">Sessions</span>
      <div className="session-picker-strip">
        {sessions === null ? (
          <>
            <div className="session-chip-skeleton" />
            <div className="session-chip-skeleton" />
            <div className="session-chip-skeleton" />
          </>
        ) : sessions.length === 0 ? (
          <span className="session-picker-empty">No sessions yet</span>
        ) : (
          sessions.map(({ uid, hasResults }) => (
            <button
              key={uid}
              type="button"
              className="session-chip"
              title={uid}
              onClick={() => onSessionSelect(uid)}
            >
              <span className={`session-chip-dot${hasResults ? " has-results" : ""}`} />
              {`…${uid.slice(-8)}`}
            </button>
          ))
        )}
      </div>
    </div>
  );
};
