/**
 * Formatting utilities for list tabs.
 * Pure functions — no Svelte runes needed.
 *
 * Ported from lighterbird's listTabFormat.js.
 * TODO: Extract to lightercore as shared library.
 */

/**
 * Format an ISO date string for display in a list.
 * - Today: shows time only
 * - This year: shows month + day
 * - Older: shows full date
 */
export function formatListItemDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 10);
    const now = new Date();
    const opts = d.toDateString() === now.toDateString()
      ? { hour: "2-digit", minute: "2-digit" }
      : d.getFullYear() === now.getFullYear()
        ? { month: "short", day: "numeric" }
        : { year: "numeric", month: "short", day: "numeric" };
    return d.toLocaleDateString([], opts);
  } catch {
    return iso.slice(0, 10);
  }
}

/**
 * Truncate a string with ellipsis if it exceeds max length.
 */
export function truncate(s, max) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max - 1) + "\u2026" : s;
}

/**
 * Extract the English label from a labels dict (JSON object or string).
 */
export function getEnglishLabel(labels) {
  if (!labels) return "";
  if (typeof labels === "string") {
    try { labels = JSON.parse(labels); } catch { return labels; }
  }
  return labels?.en || labels?.["en"] || "";
}

/**
 * Strip prefix from a node/predicate ID for compact display.
 * e.g. "http://example.org/Foo" -> "Foo", "ex:knows" -> "ex:knows"
 */
export function shortId(id) {
  if (!id) return "";
  const hashIdx = id.indexOf("#");
  if (hashIdx > 0 && hashIdx < id.length - 1) return id.slice(hashIdx + 1);
  const slashIdx = id.lastIndexOf("/");
  if (slashIdx > 0 && slashIdx < id.length - 1) return id.slice(slashIdx + 1);
  return id;
}
