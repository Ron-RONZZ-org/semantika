/** Command tree — dynamically fetched from backend. */
import { api } from "./api.js";

let _tree = null;
let _promise = null;

export function initCommandTree() {
  if (_promise) return _promise;
  _promise = api.commandTree().then((t) => { _tree = t; return t; });
  return _promise;
}

export function getCommandTree() { return _tree; }

export function getCompletions(input) {
  if (!_tree || !input) return [];
  const trimmed = input.trim().toLowerCase();
  if (!trimmed.startsWith("!")) return [];

  const parts = trimmed.slice(1).split(/\s+/);
  const prefix = parts[parts.length - 1];

  const cmds = _tree.commands || [];
  return cmds
    .filter((c) => c.path.toLowerCase().startsWith(prefix) || c.path.toLowerCase().includes(trimmed.slice(1)))
    .slice(0, 6)
    .map((c) => ({ text: `!${c.path}`, desc: c.description }));
}
