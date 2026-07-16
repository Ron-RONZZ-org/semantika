/** Command hierarchy — dynamically fetched from backend.
 *
 * Ported from lighterbird's ``commandTree.js``.
 * The authoritative tree lives in the backend and is served via
 * ``GET /api/v1/command/tree``.
 *
 * ``/`` prompt commands are handled in a completely separate path
 * (``getPromptCompletions`` in ``commandEngine.js``) and are NOT
 * appended to the command tree — the virtual ``/`` node was removed
 * to prevent ``!/`` from appearing in ``!``-mode autocomplete.
 */

export let commandTree = [];

/**
 * List of prompt commands (/ prefix) — flat array of {name, description}.
 * Populated by :func:`initPromptCommands`.
 * @type {{name:string, description:string}[]}
 */
export let promptCommands = [];

/**
 * List of triple template names for ``--template`` flag autocomplete.
 * @type {{name:string, description:string}[]}
 */
export let tripleTemplates = [];

export async function initCommandTree() {
  try {
    const resp = await fetch("/api/v1/command/tree");
    if (resp.ok) commandTree = await resp.json();
  } catch { /* Tree stays empty — commands still work via backend dispatch */ }
}

/**
 * Fetch prompt commands from the backend and populate the ``promptCommands``
 * list. Does NOT append a virtual ``/`` node to ``commandTree`` — prompt
 * command autocomplete is handled entirely by ``getPromptCompletions`` in
 * ``commandEngine.js``.
 */
export async function initPromptCommands() {
  try {
    const resp = await fetch("/api/v1/prompt-commands/list");
    if (resp.ok) {
      promptCommands = await resp.json();
    }
  } catch { /* degrade gracefully */ }
}

/**
 * Fetch triple template names for ``--template`` flag autocomplete.
 */
export async function initTripleTemplates() {
  try {
    const resp = await fetch("/api/v1/triple-templates/list");
    if (resp.ok) tripleTemplates = await resp.json();
  } catch { /* degrade gracefully */ }
}

initCommandTree();
initPromptCommands();
initTripleTemplates();

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
