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
  // Check if ANY token in the path is "add" or "write" — handles nested
  // sub-groups like "node.add.media.book" where the leaf is "book", not "add".
  // Without this, nested create commands (media, scholarly, attachment)
  // never open the interactive GUI form.
  const isAddOrWrite = effectiveTokens.some(t => t === "add" || t === "write");
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

  // Determine the command tokens actually consumed by the handler
  // (as opposed to positional params). Used by FormTab to populate DynamicForm.
  const cmdTokens = effectiveTokens.slice(0, cmdTokenCount);

  return {
    intercept: true,
    listTokens,
    listIdKey,
    addFormType,
    addTitle,
    initialData,
    commandPath: cmdTokens,
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
    // Walk up the tree to find the list command.
    // For "node add concept", parent is ["node", "add"] which has no "list"
    // child, so we try grandparent ["node"] which has "node.list".
    // For "backup config add", parent is ["backup", "config"] → "backup config list".
    for (let depth = 1; depth <= tokens.length - 1; depth++) {
      const ancestorPath = tokens.slice(0, -depth);
      const listTokens = [...ancestorPath, "list"];
      const listNode = findNode(listTokens);
      // findNode may return a partial match (last non-null ancestor).
      // Verify the resolved node is actually named "list".
      if (listNode && listNode.name === "list") return listTokens;
    }
  }

  return null;
}

function resolveListIdKey(listTokens) {
  // Derive list key from the command domain (last token before "list").
  // This avoids hardcoding every domain path — any domain ending in "list"
  // gets a key of {domain}s (e.g., "node list" -> "nodes", "backup config list" -> "backups").
  // For special plurals, override via node.listIdKey in the command tree metadata.
  if (!listTokens || listTokens.length < 2) return null;
  const domain = listTokens[listTokens.length - 2];
  // Check if the list node has an explicit listIdKey in its metadata
  const node = findNode(listTokens);
  if (node?.listIdKey) return node.listIdKey;
  // Default: simple English plural (append "s")
  return domain ? domain + "s" : null;
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

  // Legacy direct-leaft patterns (commands directly under the domain)
  if (/^node\s+add\s+concept$/i.test(path)) return "node-add";
  if (/^predicate\s+add$/i.test(path)) return "predicate-add";
  if (/^predicate\s+group\s+add$/i.test(path)) return "predicate-group-add";
  if (/^triple\s+add$/i.test(path)) return "triple-add";
  if (/^unit\s+add$/i.test(path)) return "unit-add";
  if (/^llm\s+profile\s+new$/i.test(path)) return "llm-profile-new";
  if (/^llm\s+profile\s+set$/i.test(path)) return "llm-profile-set";
  if (/^backup\s+config\s+add$/i.test(path)) return "backup-config-add";
  if (/^backup\s+config\s+modify$/i.test(path)) return "backup-config-modify";

  // Dynamic derivation for node.add sub-groups (attachment, media, scholarly, etc.)
  // Matches the backend's convention: tokens.join("-") from the dot-separated path.
  // e.g., ["node","add","media","book"] → "node-add-media-book"
  if (/^node\s+add\s+/.test(path)) {
    return tokens.join("-");
  }

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
  if (titles[addFormType]) return titles[addFormType];
  // Dynamic: "node-add-media-book" → "Add Media Book"
  const match = addFormType.match(/^node-add-(.+)$/);
  if (match) {
    const label = match[1]
      .split("-")
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    return "Add " + label;
  }
  return "Add";
}
