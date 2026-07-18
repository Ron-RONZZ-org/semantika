/**
 * Conversation utilities — message formatting and clipboard helpers.
 *
 * @module conversationUtils
 */

/**
 * Format a list of conversation messages into readable text.
 *
 * @param {Array<{role?: string, text?: string, html?: string}>} messages
 * @param {{ userLabel?: string, assistantLabel?: string }} [options]
 * @returns {string} Formatted conversation text
 */
export function formatConversationText(messages, options = {}) {
  const userLabel = options.userLabel ?? "You";
  const assistantLabel = options.assistantLabel ?? "Assistant";

  return messages
    .filter((m) => m.role)
    .map((m) => {
      const label = m.role === "user" ? userLabel : assistantLabel;
      let content = m.text;
      if (!content && m.html) {
        // Strip HTML tags for plain text fallback
        content = m.html.replace(/<[^>]*>/g, "");
      }
      return `[${label}] ${content}`;
    })
    .join("\n\n");
}

/**
 * Copy text to clipboard.  Falls back to document.execCommand("copy")
 * if the Clipboard API is unavailable or fails.
 *
 * @param {string} text
 * @returns {Promise<void>}
 */
export async function copyToClipboard(text) {
  if (!text) return;

  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Clipboard API failed — use legacy execCommand approach
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
}
