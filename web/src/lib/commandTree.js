/** Command hierarchy — dynamically fetched from backend.
 *
 * Ported from lighterbird's ``commandTree.js``.
 * The authoritative tree lives in the backend and is served via
 * ``GET /api/v1/command/tree``.
 */

export let commandTree = [];

export async function initCommandTree() {
  try {
    const resp = await fetch("/api/v1/command/tree");
    if (resp.ok) commandTree = await resp.json();
  } catch { /* Tree stays empty — commands still work via backend dispatch */ }
}

initCommandTree();

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
