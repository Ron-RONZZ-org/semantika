/** Command executor — dispatches !commands and LLM chat.
 *
 * Ported from lighterbird's ``commandExecutor.js``.
 */

import { parseCommand } from "./parser.js";

const COMMAND_ENDPOINT = "/api/v1/command";
const CHAT_ENDPOINT = "/api/v1/llm/chat";

export async function execute(input) {
  const trimmed = input.trim();
  if (!trimmed.startsWith("!")) {
    try {
      const resp = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed }),
      });
      if (!resp.ok) return { type: "error", title: "Chat Failed", data: { message: `HTTP ${resp.status}` } };
      return await resp.json();
    } catch (err) {
      return { type: "error", title: "Connection Error", data: { message: String(err) } };
    }
  }

  const { tokens, flags, partial } = parseCommand(trimmed);
  const effectiveTokens = partial ? [...tokens, partial] : tokens;
  if (effectiveTokens.length === 0) return { type: "error", title: "Error", data: { message: "No command specified." } };

  try {
    const resp = await fetch(COMMAND_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tokens: effectiveTokens, flags, raw_input: input }),
    });
    const ct = resp.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      return { type: "error", title: "Backend Error", data: { message: `Backend returned ${resp.status}` } };
    }
    const data = await resp.json();
    if (!resp.ok) {
      const detail = data.detail || {};
      const msg = typeof detail === "string" ? detail : detail.error || `HTTP ${resp.status}`;
      return { type: "error", title: "Command Failed", data: { message: msg } };
    }
    return data;
  } catch (err) {
    return { type: "error", title: "Connection Error", data: { message: String(err) } };
  }
}
