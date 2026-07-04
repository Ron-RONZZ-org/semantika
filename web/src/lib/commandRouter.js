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
  if (/^email(\s+account)?\s+list$/i.test(path)) return "accounts";
  if (/^calendar(\s+account)?\s+list$/i.test(path)) return "calendars";
  if (/^contact\s+list$/i.test(path)) return "contacts-list";
  if (/^todo\s+list$/i.test(path)) return "todo-list";
  if (/^journal\s+list$/i.test(path)) return "journal-list";
  if (/^calendar\s+list$/i.test(path)) return "calendar-events";
  if (/^email\s+list$/i.test(path)) return "email-list";
  if (/^user\s+saved-commands\s+list$/i.test(path)) return "saved-commands";
  if (/^user\s+info\s+list$/i.test(path)) return "user-info-list";
  if (/^email\s+sieve\s+list$/i.test(path)) return "sieve-list";
  if (/^email\s+signature\s+list$/i.test(path)) return "signature-list";
  if (/^letter\s+list$/i.test(path)) return "letter-list";
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
  if (/^triple\s+add$/i.test(path)) return "triple-add";
  if (/^unit\s+add$/i.test(path)) return "unit-add";
  if (/^email\s+account\s+add$/i.test(path)) return "email-account-add";
  if (/^calendar\s+account\s+add$/i.test(path)) return "calendar-account-add";
  if (/^contact\s+add$/i.test(path)) return "contacts-add";
  if (/^todo\s+add$/i.test(path)) return "todo-add";
  if (/^journal\s+write$/i.test(path)) return "journal-write";
  if (/^email\s+sieve\s+add$/i.test(path)) return "email-sieve-add";
  if (/^email\s+send$/i.test(path)) return "email-send";
  if (/^email\s+reply$/i.test(path)) return "email-send";
  if (/^email\s+forward$/i.test(path)) return "email-send";
  if (/^calendar\s+event\s+add$/i.test(path)) return "calendar-event-add";
  if (/^user\s+saved-commands\s+add$/i.test(path)) return "user-saved-commands-add";
  if (/^user\s+saved-commands\s+modify$/i.test(path)) return "user-saved-commands-modify";
  if (/^user\s+info\s+add$/i.test(path)) return "user-info-add";
  if (/^user\s+info\s+modify$/i.test(path)) return "user-info-modify";
  if (/^todo\s+template\s+add$/i.test(path)) return "todo-template-add";
  if (/^todo\s+template\s+modify$/i.test(path)) return "todo-template-modify";
  if (/^llm\s+profile\s+new$/i.test(path)) return "llm-profile-new";
  if (/^llm\s+profile\s+set$/i.test(path)) return "llm-profile-set";
  if (/^backup\s+config\s+add$/i.test(path)) return "backup-config-add";
  if (/^backup\s+config\s+modify$/i.test(path)) return "backup-config-modify";
  if (/^email\s+signature\s+add$/i.test(path)) return "email-signature-add";
  if (/^email\s+signature\s+modify$/i.test(path)) return "email-signature-modify";
  if (/^letter\s+add$/i.test(path)) return "letter-add";
  if (/^letter\s+send$/i.test(path)) return "letter-send";

  return leafName;
}

function resolveAddTitle(addFormType) {
  const titles = {
    "node-add": "Add Node",
    "predicate-add": "Add Predicate",
    "triple-add": "Add Triple",
    "unit-add": "Add Unit",
    "email-account-add": "Add Email Account",
    "calendar-account-add": "Add Calendar Account",
    "contacts-add": "Add Contact",
    "todo-add": "Add Todo",
    "journal-write": "Write Journal Entry",
    "email-sieve-add": "Add Sieve Script",
    "email-send": "Compose Email",
    "calendar-event-add": "Add Calendar Event",
    "user-saved-commands-add": "New Saved Command",
    "user-saved-commands-modify": "Edit Saved Command",
    "user-info-add": "Add User Profile",
    "user-info-modify": "Modify User Profile",
    "todo-template-add": "New Todo Template",
    "todo-template-modify": "Edit Todo Template",
    "llm-profile-new": "New LLM Profile",
    "llm-profile-set": "Set LLM Profile",
    "backup-config-add": "Add Backup Strategy",
    "backup-config-modify": "Modify Backup Strategy",
    "email-signature-add": "Add Email Signature",
    "email-signature-modify": "Modify Email Signature",
    "letter-add": "Add Received Letter",
    "letter-send": "Send Letter",
  };
  return titles[addFormType] || "Add";
}
