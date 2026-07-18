/**
 * TripleAddTypeUtils — Pure functions for the dual-path type system
 * in TripleAddTab.
 *
 * These functions are extracted for testability. They map between
 * CLI --flag words and the row metadata (object_type, object_datatype).
 *
 * @module tripleAddTypeUtils
 */

/**
 * Maps CLI flag words (lowercase) to type metadata.
 *
 * Abbreviations are accepted (e.g., "str" → same as "string").
 */
export const TYPE_FLAG_MAP = {
  "string":  { object_type: "literal", object_datatype: null },
  "str":     { object_type: "literal", object_datatype: null },
  "int":     { object_type: "literal", object_datatype: "xsd:integer" },
  "float":   { object_type: "literal", object_datatype: "xsd:decimal" },
  "bool":    { object_type: "literal", object_datatype: "xsd:boolean" },
  "url":     { object_type: "literal", object_datatype: "xsd:anyURI" },
  "katex":   { object_type: "literal", object_datatype: "text/katex" },
};

/**
 * Resolve a --flag word to type metadata.
 *
 * @param {string} word - The flag word (e.g., "string", "str", "int").
 * @returns {{ object_type: string, object_datatype: string|null }|null}
 *   Type metadata object, or null for unknown flags.
 */
export function interpretFlag(word) {
  return TYPE_FLAG_MAP[word.toLowerCase()] || null;
}

/**
 * Parse a --flag prefix from an object input value.
 *
 * Efficiency hack: only triggers on "--WORD " (flag followed by SPACE)
 * so the user can complete the flag word before interpretation fires.
 *
 * Edge cases handled:
 *   - "" → { flag: null, rest: "" }
 *   - "hello" → { flag: null, rest: "hello" }
 *   - "--int" → { flag: null, rest: "--int" }       (no space — still typing)
 *   - "--int " → { flag: "int", rest: "" }
 *   - "--int 42" → { flag: "int", rest: "42" }
 *   - "--str hello world" → { flag: "str", rest: "hello world" }
 *   - "--invalid abc" → { flag: "invalid", rest: "abc" }
 *
 * @param {string} raw - The raw input value.
 * @returns {{ flag: string|null, rest: string }}
 */
export function parseFlagFromValue(raw) {
  if (!raw || !raw.startsWith("--")) return { flag: null, rest: raw };
  const match = raw.match(/^--(\w+)\s+/);
  if (!match) return { flag: null, rest: raw };
  return { flag: match[1].toLowerCase(), rest: raw.slice(match[0].length) };
}

/**
 * Resolve the display type ID from a row's type metadata.
 *
 * @param {{ object_type: string, object_datatype: string|null }} row
 * @returns {string} One of: "node", "literal", "int", "float", "bool", "url", "katex"
 */
export function resolveObjectType(row) {
  const ot = row.object_type;
  if (ot !== "literal") return ot;
  const dt = row.object_datatype;
  if (dt === "xsd:integer") return "int";
  if (dt === "xsd:decimal") return "float";
  if (dt === "xsd:boolean") return "bool";
  if (dt === "xsd:anyURI") return "url";
  if (dt === "text/katex") return "katex";
  return "literal";
}

/**
 * Display labels for each type ID.
 */
export const OBJECT_TYPE_LABELS = {
  node: "Node", literal: "Str", int: "Int",
  float: "Float", bool: "Bool", url: "URL", katex: "KaTeX",
};

/**
 * Boolean literal value suggestions for the OBJECT datalist.
 *
 * @returns {{ id: string, label: string }[]}
 */
export function getBoolSuggestions() {
  return [
    { id: "true", label: "True" },
    { id: "false", label: "False" },
  ];
}

/**
 * Get the complete list of CLI --flag suggestions for the OBJECT datalist.
 *
 * Deduplicates by key since TYPE_FLAG_MAP may have multiple keys for the
 * same type (e.g., "string" and "str").
 *
 * @returns {string[]} Sorted list of unique --flag strings
 */
export function getFlagSuggestions() {
  const seen = new Set();
  const result = [];
  for (const key of Object.keys(TYPE_FLAG_MAP)) {
    if (!seen.has(key)) {
      seen.add(key);
      result.push(`--${key}`);
    }
  }
  return result.sort();
}

/**
 * OBJECT_TYPE_ITEMS for rendering the `<select>` dropdown options.
 */
export const OBJECT_TYPE_ITEMS = [
  { id: "node",    label: "Node",  icon: "\u{1F310}" },
  { id: "literal", label: "Str",   icon: "\u201C" },
  { id: "int",     label: "Int",   icon: "#" },
  { id: "float",   label: "Float", icon: "#.#" },
  { id: "bool",    label: "Bool",  icon: "\u2713/\u2717" },
  { id: "url",     label: "URL",   icon: "\u{1F517}" },
  { id: "katex",   label: "KaTeX", icon: "\u03C0" },
];
