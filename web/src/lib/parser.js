/** Parser — tokenizes !commands into tokens, flags, and cursor position.
 *
 * Ported from lighterbird's ``parser.js``.
 */

export function parseCommand(input) {
  const trimmed = input.trim();
  if (!trimmed || !trimmed.startsWith("!")) {
    return { tokens: [], flags: {}, partial: trimmed.replace(/^!/, "") };
  }

  const withoutBang = trimmed.slice(1).trimStart();
  const tokens = [];
  const flags = {};
  let partial = "";
  let inFlag = null;
  let inQuote = false;
  let current = "";
  let i = 0;
  const trailing = input.endsWith(" ");

  function flush() {
    if (current === "") return;
    if (current.startsWith("--") && inFlag === null) {
      inFlag = current.slice(2); current = "";
    } else if (inFlag !== null) {
      flags[inFlag] = current; inFlag = null; current = "";
    } else {
      tokens.push(current); current = "";
    }
  }

  while (i < withoutBang.length) {
    const ch = withoutBang[i];
    if (ch === '"') {
      if (inQuote) { inQuote = false; flush(); }
      else {
        inQuote = true;
        if (current !== "") {
          const eqIdx = current.indexOf("=");
          if (current.startsWith("--") && eqIdx > 0) {
            inFlag = current.slice(2, eqIdx); current = "";
          } else { flush(); }
        }
      }
    } else if (inQuote) { current += ch; }
    else if (ch === " " || ch === "\t") { flush(); }
    else if (ch === "=" && current.startsWith("--")) { inFlag = current.slice(2); current = ""; }
    else { current += ch; }
    i++;
  }

  if (inQuote) { partial = current; }
  else if (current !== "") {
    if (current.startsWith("--")) { partial = current; }
    else if (inFlag !== null) { flags[inFlag] = current; }
    else if (trailing) { tokens.push(current); }
    else { partial = current; }
  } else if (inFlag !== null) { flags[inFlag] = ""; }

  return { tokens, flags, partial };
}

export function hasTrailingSpace(input) {
  return input.endsWith(" ");
}

/**
 * Parse a prompt command (/ prefix) into name and args.
 * Returns null if input does not start with "/".
 */
export function parsePromptCommand(input) {
  const trimmed = input.trim();
  if (!trimmed.startsWith("/")) return null;
  const rest = trimmed.slice(1).trimStart();
  if (!rest) return { name: "", args: [] };
  const parts = rest.split(/\s+/);
  return { name: parts[0], args: parts.slice(1) };
}
