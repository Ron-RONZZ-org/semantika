/**
 * Format a command item (tokens + flags) into a human-readable string.
 *
 * @param {{tokens?: string[], flags?: Record<string,string>}} item
 * @returns {string} e.g. "!node add --label Alice"
 */
export function formatCommand(item) {
  const tokens = item.tokens || [];
  const flags = item.flags || {};
  let cmd = "!" + tokens.join(" ");
  for (const [k, v] of Object.entries(flags)) {
    cmd += v ? ` --${k} ${v}` : ` --${k}`;
  }
  return cmd;
}
