/** Command router — intercepts add/write commands with missing params.
 *
 * Ported from lighterbird's ``commandRouter.js``.
 */

import { parseCommand, hasTrailingSpace } from "./parser.js";
import { findNode, commandTree } from "./commandTree.js";

export function shouldIntercept(input) {
  const trimmed = input.trim();
  if (!trimmed.startsWith("!")) return { intercept: false };

  const { tokens, flags, partial } = parseCommand(trimmed);
  const trailing = hasTrailingSpace(trimmed);
  let effectiveTokens = tokens;
  if (trailing && partial) effectiveTokens = [...tokens, partial];
  else if (!trailing && partial && findNode([...tokens, partial])) effectiveTokens = [...tokens, partial];

  if (effectiveTokens.length === 0) return { intercept: false };
  const node = findNode(effectiveTokens);
  if (!node) return { intercept: false };

  const leafName = effectiveTokens[effectiveTokens.length - 1];
  const isAddOrWrite = leafName === "add" || leafName === "write";
  const isInteractive = node.interactive === true;
  if (!isAddOrWrite && !isInteractive) return { intercept: false };

  const cmdTokenCount = countCommandTokens(effectiveTokens);
  const consumed = effectiveTokens.length - cmdTokenCount;
  const missingRequiredParam = node.params?.some((p, i) => p.required && i >= consumed);
  const missingRequiredFlag = node.flags?.some((f) => f.required && !(f.name in flags));
  if (!missingRequiredParam && !missingRequiredFlag) return { intercept: false };

  const listTokens = resolveListCommand(node, effectiveTokens);
  if (!listTokens) return { intercept: false };

  const paramTokens = effectiveTokens.slice(cmdTokenCount);
  const initialData = buildInitialData(node, leafName, paramTokens, flags);
  const addFormType = resolveAddFormType(effectiveTokens);

  return { intercept: true, listTokens, addFormType, initialData };
}

function countCommandTokens(tokens) {
  let current = commandTree;
  for (let i = 0; i < tokens.length; i++) {
    const found = current.find((n) => n.name.toLowerCase() === tokens[i].toLowerCase());
    if (!found) return i;
    if (!found.children || found.children.length === 0) return i + 1;
    current = found.children || [];
  }
  return tokens.length;
}

function resolveListCommand(node, tokens) {
  if (node.listCommand && Array.isArray(node.listCommand)) return node.listCommand;
  const leafName = tokens[tokens.length - 1];
  if (leafName === "add" || leafName === "write") {
    const listTokens = tokens.slice(0, -1); listTokens.push("list");
    if (findNode(listTokens)) return listTokens;
  }
  return null;
}

function buildInitialData(node, leafName, paramTokens, flags) {
  const data = {};
  if (node.params) {
    for (let i = 0; i < paramTokens.length && i < node.params.length; i++) {
      data[node.params[i].name] = paramTokens[i];
    }
  }
  for (const [key, val] of Object.entries(flags)) {
    if (val && typeof val === "string" && val.length > 0) data[key] = val;
  }
  return data;
}

function resolveAddFormType(tokens) {
  const path = tokens.join(" ");
  if (/^node\s+add$/i.test(path)) return "node-add";
  if (/^predicate\s+add$/i.test(path)) return "predicate-add";
  if (/^triple\s+add$/i.test(path)) return "triple-add";
  if (/^unit\s+add$/i.test(path)) return "unit-add";
  return tokens[tokens.length - 1];
}
