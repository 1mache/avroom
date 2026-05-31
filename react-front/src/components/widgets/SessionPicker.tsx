import React, { useEffect, useState } from "react";
import { getSessions, getUidCacheStatus } from "../../api/images";

interface SessionMeta {
  uid: string;
  name: string | null;
  // Precomputed summary bit so render path does not need to know cache schema.
  hasResults: boolean;
}

interface SessionPickerProps {
  onSessionSelect: (uid: string) => void;
  /** Increment to force a re-fetch of the session list (e.g. after upload). */
  refreshKey: number;
}

export const SessionPicker: React.FC<SessionPickerProps> = ({ onSessionSelect, refreshKey }) => {
  const [sessions, setSessions] = useState<SessionMeta[] | null>(null);

  useEffect(() => {
    let cancelled = false;

    getSessions()
      .then(async (infos) => {
        if (cancelled) return;

        // Enrich raw session ids with cheap cache metadata so UI can hint whether
        // a session already has background/cutout artifacts ready.
        const metas = await Promise.all(
          infos.map(async ({ uid, name }): Promise<SessionMeta> => {
            try {
              const status = await getUidCacheStatus(uid);
              return { uid, name, hasResults: status.has_background || status.has_cutout };
            } catch {
              return { uid, name, hasResults: false };
            }
          }),
        );

        if (!cancelled) {
          setSessions(metas);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSessions([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const getLabel = (uid: string, name: string | null): string => {
    if (name) return name;
    return uid.length > 8 ? `${uid.slice(0, 8)}...` : uid;
  };

  return (
    <div className="session-picker">
      <span className="session-picker-label">Previous sessions</span>
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
          sessions.map(({ uid, name, hasResults }) => (
            <button
              key={uid}
              type="button"
              className="session-chip"
              title={uid}
              onClick={() => onSessionSelect(uid)}
            >
              <span className={`session-chip-dot${hasResults ? " has-results" : ""}`} />
              {getLabel(uid, name)}
            </button>
          ))
        )}
      </div>
    </div>
  );
};
