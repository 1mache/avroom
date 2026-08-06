/**
 * Coarse relative-time label, e.g. "edited 5m ago". Deliberately approximate —
 * this is a hint about how fresh a session is, not a clock.
 */
export const formatEditedAgo = (iso: string | null): string | null => {
  if (!iso) {
    return null;
  }

  const then = Date.parse(iso);
  if (Number.isNaN(then)) {
    return null;
  }

  const diffMinutes = Math.floor((Date.now() - then) / 60000);
  if (diffMinutes < 1) return "edited just now";
  if (diffMinutes < 60) return `edited ${diffMinutes}m ago`;

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `edited ${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  return `edited ${diffDays}d ago`;
};

/** Newest first; sessions the server never timestamped sort last. */
export const byMostRecentlyEdited = (
  a: { last_changed: string | null },
  b: { last_changed: string | null },
): number => {
  const at = a.last_changed ? Date.parse(a.last_changed) : Number.NEGATIVE_INFINITY;
  const bt = b.last_changed ? Date.parse(b.last_changed) : Number.NEGATIVE_INFINITY;
  return bt - at;
};
