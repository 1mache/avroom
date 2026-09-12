import type { ConflictNotice } from "../../hooks/useConflictNotices";

export interface NoticeStackProps {
  notices: ConflictNotice[];
  onDismiss: (id: number) => void;
}

/**
 * Transient inline notices, stacked over the stage.
 *
 * Used for job conflicts -- a mask overlapping an in-flight removal -- which
 * are expected enough that a modal would be the wrong weight.
 */
export const NoticeStack: React.FC<NoticeStackProps> = ({ notices, onDismiss }) => {
  if (notices.length === 0) {
    return null;
  }
  return (
    <div className="notice-stack">
      {notices.map((notice) => (
        <div key={notice.id} className="notice">
          <span>{notice.message}</span>
          <button
            type="button"
            className="notice-dismiss"
            onClick={() => onDismiss(notice.id)}
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
};
