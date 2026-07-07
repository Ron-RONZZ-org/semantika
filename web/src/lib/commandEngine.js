/** Command completion engine — level-by-level suggestions.
 *
 * Levels: 0=root, 1-N=children, N+1=params/flags
 * Ported from lighterbird's ``commandEngine.js``.
 */

import { commandTree, promptCommands, findNode, matchChildren } from "./commandTree.js";
import { parseCommand, parsePromptCommand, hasTrailingSpace } from "./parser.js";

export function getCompletions(input) {
  const { tokens, flags, partial } = parseCommand(input);
  const trailing = hasTrailingSpace(input);
  const effectiveTokens = trailing && partial ? [...tokens, partial] : tokens;
  const effectivePartial = trailing ? "" : partial;

  if (effectiveTokens.length === 0 && !trailing) {
    const prefix = effectivePartial.replace(/^!/, "");
    if (!prefix) return { completions: commandTree.map((n) => `!${n.name}`), hints: commandTree.map((n) => n.description || ""), node: null, level: "root", positionals: [] };
    const matches = matchChildren(commandTree, prefix);
    return { completions: matches.map((n) => `!${n.name}`), hints: matches.map((n) => n.description || ""), node: null, level: "root", positionals: [] };
  }
  if (effectiveTokens.length === 0 && trailing) {
    return { completions: commandTree.map((n) => `!${n.name}`), hints: commandTree.map((n) => n.description || ""), node: null, level: "root", positionals: [] };
  }

  const node = findNode(effectiveTokens);
  if (!node) {
    const parent = findNode(effectiveTokens.slice(0, -1));
    const partialToken = effectiveTokens[effectiveTokens.length - 1];
    if (parent && parent.children) {
      const matches = matchChildren(parent.children, partialToken);
      return { completions: matches.map((n) => n.name), hints: matches.map((n) => n.description || ""), node: null, level: "child", positionals: [] };
    }
    if (!parent) {
      const matches = matchChildren(commandTree, partialToken);
      return { completions: matches.map((n) => `!${n.name}`), hints: matches.map((n) => n.description || ""), node: null, level: "root", positionals: [] };
    }
    return { completions: [], hints: [], node: null, level: "root", positionals: [] };
  }

  if (node.children) {
    if (trailing) return { completions: node.children.map((c) => c.name), hints: node.children.map((c) => c.description || ""), node, level: "child", positionals: [] };
    if (effectivePartial) {
      const matches = matchChildren(node.children, effectivePartial);
      return { completions: matches.map((c) => c.name), hints: matches.map((c) => c.description || ""), node, level: "child", positionals: [] };
    }
    return { completions: [], hints: [], node, level: "child", positionals: [] };
  }

  if (trailing || effectivePartial) {
    const consumed = effectiveTokens.slice(findNodeIndex(effectiveTokens) + 1);
    const paramHints = buildParamHints(node, consumed, flags, effectivePartial);
    const posInfo = buildPositionalInfo(node, consumed);
    return { completions: paramHints.map((h) => h.text), hints: paramHints.map((h) => h.desc), node, level: "params", positionals: posInfo };
  }
  return { completions: [], hints: [], node, level: "params", positionals: [] };
}

function buildPositionalInfo(node, consumedTokens) {
  if (!node.params || node.params.length === 0) return [];
  return node.params.map((p, i) => ({ name: p.name, entered: i < consumedTokens.length, required: p.required }));
}

function buildParamHints(node, consumedTokens, flags, partial = "") {
  const hints = [];
  const isFlagPartial = partial.startsWith("--");
  if (isFlagPartial) {
    const partialFlag = partial.slice(2).toLowerCase();
    if (node.flags) {
      for (const f of node.flags) {
        if (f.name.toLowerCase().startsWith(partialFlag)) hints.push({ text: `--${f.name}`, desc: `${f.short ? `-${f.short}, ` : ""}${f.help || f.type}` });
      }
    }
    return hints;
  }
  if (!partial && node.flags) {
    const usedFlags = new Set(Object.keys(flags));
    for (const f of node.flags) {
      if (!usedFlags.has(f.name)) hints.push({ text: `--${f.name}`, desc: `${f.short ? `-${f.short}, ` : ""}${f.help || f.type}` });
    }
  }
  return hints;
}

function findNodeIndex(tokens) {
  let current = commandTree;
  for (let i = 0; i < tokens.length; i++) {
    const found = current.find((n) => n.name.toLowerCase() === tokens[i].toLowerCase());
    if (!found) return i - 1;
    if (!found.children || found.children.length === 0) return i;
    current = found.children || [];
  }
  return tokens.length - 1;
}

/**
 * Get autocomplete completions for prompt commands (/ prefix).
 */
export function getPromptCompletions(input) {
  const parsed = parsePromptCommand(input);
  if (!parsed) return { completions: [], hints: [] };
  const prefix = parsed.name.toLowerCase();
  if (!prefix) {
    return {
      completions: promptCommands.map((c) => `/${c.name}`),
      hints: promptCommands.map((c) => c.description || ""),
    };
  }
  // Exclude exact matches — once the user has typed the full command name,
  // there's nothing to autocomplete; showing the same command again traps them
  // in a fill loop on Enter.
  const matches = promptCommands.filter((c) =>
    c.name.toLowerCase().startsWith(prefix) && c.name.toLowerCase() !== prefix,
  );
  return {
    completions: matches.map((c) => `/${c.name}`),
    hints: matches.map((c) => c.description || ""),
  };
}


