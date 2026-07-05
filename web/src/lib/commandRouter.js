import { parseCommand, hasTrailingSpace } from "./parser.js";
import { findNode, commandTree } from "./commandTree.js";

export function shouldIntercept(input) {
  const trimmed = input.trim();
  if (!trimmed.startsWith("!")) return { intercept: false };

  const { tokens, flags, partial } = parseCommand(trimmed);
  const trailing = hasTrailingSpace(trimmed);

  let effectiveTokens = tokens;
  if (trailing && partial) {
    effectiveTokens = [...tokens, partial];
  } else if (!trailing && partial) {
    const nodeWithPartial = findNode([...tokens, partial]);
    if (nodeWithPartial) {
      effectiveTokens = [...tokens, partial];
    }
  }

  if (effectiveTokens.length === 0) return { intercept: false };

  const node = findNode(effectiveTokens);
  if (!node) return { intercept: false };

  const leafName = effectiveTokens[effectiveTokens.length - 1];
  const isAddOrWrite = leafName === "add" || leafName === "write";
  const isInteractive = node.interactive === true;
  if (!isAddOrWrite && !isInteractive) return { intercept: false };

  const cmdTokenCount = countCommandTokens(effectiveTokens);
  const consumed = effectiveTokens.length - cmdTokenCount;

  const missingRequiredParam = node.params?.some(
    (p, i) => p.required && i >= consumed,
  );

  const missingRequiredFlag = node.flags?.some(
    (f) => f.required && !(f.name in flags),
  );

  // For "add" commands, always show the form (skip missing-params check)
  // for other commands, only intercept when required params/flags are missing
  if (!isAddOrWrite && !missingRequiredParam && !missingRequiredFlag) return { intercept: false };

  const listTokens = resolveListCommand(node, effectiveTokens);
  if (!listTokens) return { intercept: false };

  const listIdKey = resolveListIdKey(listTokens);

  const paramTokens = effectiveTokens.slice(cmdTokenCount);
  const initialData = buildInitialData(node, leafName, paramTokens, flags);

  const addFormType = resolveAddFormType(effectiveTokens, leafName);
  const addTitle = resolveAddTitle(addFormType);

  return {
    intercept: true,
    listTokens,
    listIdKey,
    addFormType,
    addTitle,
    initialData,
  };
}

function countCommandTokens(tokens) {
  let current = commandTree;
  for (let i = 0; i < tokens.length; i++) {
    const found = current.find(
      (n) => n.name.toLowerCase() === tokens[i].toLowerCase(),
    );
    if (!found) return i;
    if (!found.children || found.children.length === 0) return i + 1;
    current = found.children || [];
  }
  return tokens.length;
}

function resolveListCommand(node, tokens) {
  if (node.listCommand && Array.isArray(node.listCommand)) {
    return node.listCommand;
  }

  const leafName = tokens[tokens.length - 1];
  if (leafName === "add" || leafName === "write") {
    const listTokens = tokens.slice(0, -1);
    listTokens.push("list");
    const listNode = findNode(listTokens);
    if (listNode) return listTokens;
  }

  if (node.interactive && tokens.length >= 2) {
    const domain = tokens[0];
    const listTokens = [domain, "list"];
    const listNode = findNode(listTokens);
    if (listNode) return listTokens;
  }

  return null;
}

function resolveListIdKey(listTokens) {
  const path = listTokens.join(" ");
  if (/^node\s+list$/i.test(path)) return "nodes";
  if (/^predicate\s+list$/i.test(path)) return "predicates";
  if (/^triple\s+list$/i.test(path)) return "triples";
  if (/^unit\s+list$/i.test(path)) return "units";
  return null;
}

function buildInitialData(node, leafName, paramTokens, flags) {
  const data = {};

  if (node.params) {
    for (let i = 0; i < paramTokens.length && i < node.params.length; i++) {
      const paramName = node.params[i].name;
      data[paramName] = paramTokens[i];
    }
  }

  for (const [key, val] of Object.entries(flags)) {
    if (val && typeof val === "string" && val.length > 0) {
      data[key] = val;
    }
  }

  return data;
}

function resolveAddFormType(tokens, leafName) {
  const path = tokens.join(" ");

  if (/^node\s+add$/i.test(path)) return "node-add";
  if (/^predicate\s+add$/i.test(path)) return "predicate-add";
  if (/^predicate\s+group\s+add$/i.test(path)) return "predicate-group-add";
  if (/^triple\s+add$/i.test(path)) return "triple-add";
  if (/^unit\s+add$/i.test(path)) return "unit-add";
  if (/^llm\s+profile\s+new$/i.test(path)) return "llm-profile-new";
  if (/^llm\s+profile\s+set$/i.test(path)) return "llm-profile-set";
  if (/^backup\s+config\s+add$/i.test(path)) return "backup-config-add";
  if (/^backup\s+config\s+modify$/i.test(path)) return "backup-config-modify";

  return leafName;
}

function resolveAddTitle(addFormType) {
  const titles = {
    "node-add": "Add Node",
    "predicate-add": "Add Predicate",
    "triple-add": "Add Triple",
    "unit-add": "Add Unit",
    "llm-profile-new": "New LLM Profile",
    "llm-profile-set": "Set LLM Profile",
    "backup-config-add": "Add Backup Strategy",
    "backup-config-modify": "Modify Backup Strategy",
  };
  return titles[addFormType] || "Add";
}
