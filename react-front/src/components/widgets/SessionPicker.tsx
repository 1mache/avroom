import React, { useEffect, useState } from "react";
import { getSessions, getUidCacheStatus } from "../../api/images";

interface SessionMeta {
  uid: string;
  name: string | null;
  lastChanged: string | null;
  // Precomputed summary bit so render path does not need to know cache schema.
  hasResults: boolean;
}

// Coarse relative-time label for the session chip, e.g. "edited 5m ago".
// Deliberately approximate — this is a hint, not a clock.
const formatEditedAgo = (iso: string | null): string | null => {
  if (!iso) {
    return null;
  }

  const then = Date.parse(iso);
  if (Number.isNaN(then)) {
    return null;
  }

  const diffMs = Date.now() - then;
  const diffMinutes = Math.floor(diffMs / 60000);

  if (diffMinutes < 1) return "edited just now";
  if (diffMinutes < 60) return `edited ${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `edited ${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `edited ${diffDays}d ago`;
};

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
          infos.map(async ({ uid, name, last_changed: lastChanged }): Promise<SessionMeta> => {
            try {
              const status = await getUidCacheStatus(uid);
              return {
                uid,
                name,
                lastChanged,
                hasResults: status.has_background || status.has_cutout,
              };
            } catch {
              return { uid, name, lastChanged, hasResults: false };
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
          sessions.map(({ uid, name, lastChanged, hasResults }) => {
            const editedAgo = formatEditedAgo(lastChanged);
            return (
              <button
                key={uid}
                type="button"
                className="session-chip"
                title={editedAgo ? `${uid} — ${editedAgo}` : uid}
                onClick={() => onSessionSelect(uid)}
              >
                <span className={`session-chip-dot${hasResults ? " has-results" : ""}`} />
                <span className="session-chip-label">{getLabel(uid, name)}</span>
                {editedAgo ? <span className="session-chip-edited">{editedAgo}</span> : null}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
};
