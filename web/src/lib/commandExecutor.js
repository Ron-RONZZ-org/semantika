/** Command executor — dispatches to backend. */
import { api } from "./api.js";

export async function execute(input) {
  const trimmed = input.trim();
  if (!trimmed) return { type: "error", message: "Empty command" };

  // If it starts with !, treat as command
  if (trimmed.startsWith("!")) {
    const cmd = trimmed.slice(1);
    return api.execute(cmd);
  }

  // Otherwise, treat as LLM chat
  try {
    const result = await api.chat(trimmed);
    return { type: "chat", data: result };
  } catch (err) {
    return { type: "error", message: String(err) };
  }
}
