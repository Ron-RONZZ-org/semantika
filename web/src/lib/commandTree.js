/** Command hierarchy — dynamically fetched from backend.
 *
 * Ported from lighterbird's ``commandTree.js``.
 * The authoritative tree lives in the backend and is served via
 * ``GET /api/v1/command/tree``.
 *
 * ``/`` prompt commands are also fetched from the backend and appended as
 * a virtual root node. See :func:`initPromptCommands`.
 */

export let commandTree = [];

/**
 * List of prompt commands (/ prefix) — flat array of {name, description}.
 * Populated by :func:`initPromptCommands`.
 * @type {{name:string, description:string}[]}
 */
export let promptCommands = [];

export async function initCommandTree() {
  try {
    const resp = await fetch("/api/v1/command/tree");
    if (resp.ok) commandTree = await resp.json();
  } catch { /* Tree stays empty — commands still work via backend dispatch */ }
}

/**
 * Fetch prompt commands from the backend and populate the ``promptCommands``
 * list. Also appends a virtual ``/`` node to ``commandTree`` for autocomplete.
 */
export async function initPromptCommands() {
  try {
    const resp = await fetch("/api/v1/prompt-commands/list");
    if (resp.ok) {
      const cmds = await resp.json();
      promptCommands = cmds;
      // Append virtual / root node
      if (cmds.length > 0) {
        const existing = commandTree.find((n) => n.name === "/");
        if (!existing) {
          commandTree.push({
            name: "/",
            description: "Prompt commands",
            children: cmds.map((c) => ({
              name: c.name,
              description: c.description,
            })),
          });
        }
      }
    }
  } catch { /* degrade gracefully */ }
}

initCommandTree();
initPromptCommands();

export function getRootNames() {
  return commandTree.map((n) => n.name);
}

export function findNode(tokens) {
  let current = commandTree;
  let node = null;
  for (const token of tokens) {
    const matched = current.find((n) => n.name.toLowerCase() === token.toLowerCase());
    if (!matched) return node;
    node = matched;
    if (!node.children || node.children.length === 0) return node;
    current = node.children;
  }
  return node;
}

export function matchChildren(nodes, prefix) {
  const p = prefix.toLowerCase();
  return nodes.filter((n) => n.name.toLowerCase().startsWith(p));
}
