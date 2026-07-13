/**
 * SPARQL CodeMirror 6 language support with Wikidata-style autocomplete.
 *
 * Builds on @codemirror/lang-sql with SPARQL-specific keywords.
 * Exports:
 *   - sparql() — CodeMirror language extension for syntax highlighting
 *   - sparqlAutocomplete() — CompletionSource for context-aware autocomplete
 *     (SPARQL keywords + known RDF prefixes + entity search from backend)
 */

import { SQLite, sql } from "@codemirror/lang-sql";
import { autocompletion } from "@codemirror/autocomplete";

// ---------------------------------------------------------------------------
// SPARQL keywords
// ---------------------------------------------------------------------------

const SPARQL_KEYWORDS = [
  "BASE", "PREFIX", "SELECT", "CONSTRUCT", "DESCRIBE", "ASK",
  "FROM", "NAMED", "WHERE", "ORDER", "BY", "ASC", "DESC",
  "LIMIT", "OFFSET", "DISTINCT", "REDUCED",
  "FILTER", "OPTIONAL", "UNION", "GRAPH", "SERVICE", "SILENT",
  "BIND", "IN", "NOT", "EXISTS", "MINUS",
  "REGEX", "STR", "LANG", "LANGMATCHES", "DATATYPE", "BOUND",
  "IRI", "URI", "BNODE", "RAND", "ABS", "CEIL", "FLOOR", "ROUND",
  "CONCAT", "SUBSTR", "STRLEN", "UCASE", "LCASE",
  "ENCODE_FOR_URI", "CONTAINS", "STRSTARTS", "STRENDS",
  "STRBEFORE", "STRAFTER",
  "YEAR", "MONTH", "DAY", "HOURS", "MINUTES", "SECONDS",
  "TIMEZONE", "TZ", "NOW", "UUID", "STRUUID",
  "MD5", "SHA1", "SHA256", "SHA384", "SHA512",
  "COALESCE", "IF", "STRLANG", "STRDT",
  "ISIRI", "ISURI", "ISBLANK", "ISLITERAL", "ISNUMERIC", "SAMETERM",
  "TRUE", "FALSE", "UNDEF",
  "SEPARATOR", "GROUP_CONCAT", "SAMPLE", "SUM", "MIN", "MAX", "AVG", "COUNT",
  "GROUP", "HAVING",
];

// ---------------------------------------------------------------------------
// Known RDF prefixes
// ---------------------------------------------------------------------------

const KNOWN_PREFIXES = [
  { prefix: "rdf", uri: "http://www.w3.org/1999/02/22-rdf-syntax-ns#" },
  { prefix: "rdfs", uri: "http://www.w3.org/2000/01/rdf-schema#" },
  { prefix: "xsd", uri: "http://www.w3.org/2001/XMLSchema#" },
  { prefix: "owl", uri: "http://www.w3.org/2002/07/owl#" },
  { prefix: "skos", uri: "http://www.w3.org/2004/02/skos/core#" },
  { prefix: "foaf", uri: "http://xmlns.com/foaf/0.1/" },
  { prefix: "dc", uri: "http://purl.org/dc/elements/1.1/" },
  { prefix: "dct", uri: "http://purl.org/dc/terms/" },
];

/** Full PREFIX declaration lines as completion options. */
function prefixOptions(all) {
  return all.map((p) => ({
    label: `PREFIX ${p.prefix}: <${p.uri}>`,
    type: "keyword",
    detail: `PREFIX ${p.prefix}`,
    apply: `PREFIX ${p.prefix}: <${p.uri}>`,
  }));
}

/** Short prefix:name completions. */
function prefixShortOptions(all) {
  return all.map((p) => ({
    label: `${p.prefix}:`,
    type: "namespace",
    detail: p.uri,
  }));
}

/** SPARQL keyword completions. */
const keywordOptions = SPARQL_KEYWORDS.map((kw) => ({
  label: kw,
  type: "keyword",
  boost: kw === "SELECT" || kw === "WHERE" || kw === "PREFIX" ? 99 : 50,
}));

// ---------------------------------------------------------------------------
// Entity autocomplete — fetches from backend
// ---------------------------------------------------------------------------

const AUTOCOMPLETE_ENDPOINT = "/api/v1/query/sparql/autocomplete";

/** Simple in-memory cache for entity search (cleared after 30s). */
let entityCache = { query: "", type: "", results: [], timestamp: 0 };
const CACHE_TTL = 30000;

/**
 * Guess the triple position at the cursor by scanning backward.
 *
 * In a SPARQL triple pattern ``?s ?p ?o`` the three positions are:
 *   - 0 (subject) → suggest **nodes**
 *   - 1 (predicate) → suggest **predicates**
 *   - 2 (object) → suggest **nodes** (or both)
 *
 * Heuristic: scan backward from the cursor to the last structural delimiter
 * (``{``, ``.``, ``;``, ``}``), tokenise, filter out SPARQL keywords, and
 * count the remaining terms.
 *
 * @param {import("@codemirror/autocomplete").CompletionContext} context
 * @returns {"node"|"predicate"|""} The inferred entity type filter, or ``""``
 *   when the position cannot be determined.
 */
function guessPosition(context) {
  // Scan backward up to 200 chars to find the last delimiter
  const before = context.state.sliceDoc(
    Math.max(0, context.pos - 200),
    context.pos,
  );

  // Find the last structural delimiter
  const delimMatch = before.match(
    /[{}.]\s*[^;{}.]*$/,
  );
  const relevant = delimMatch ? delimMatch[0] : before;

  // Tokenise: split on whitespace, filter SPARQL keywords and punctuation
  const tokens = relevant
    .split(/\s+/)
    .map((t) => t.replace(/^[{}()[\];,.]/, "").replace(/[{}()[\];,.]$/, ""))
    .filter((t) => t.length > 0 && !/^(SELECT|WHERE|FILTER|OPTIONAL|UNION|GRAPH|SERVICE|BIND|VALUES|LIMIT|OFFSET|ORDER|BY|ASC|DESC|HAVING|GROUP|PREFIX|BASE|FROM|NAMED|CONSTRUCT|DESCRIBE|ASK|DISTINCT|REDUCED|AS|MINUS|NOT|IN|EXISTS|a)$/i.test(t));

  // Count remaining non-keyword tokens
  const nonKeywordCount = tokens.length;

  // Position 0 (subject) → nodes
  if (nonKeywordCount <= 1) return "node";
  // Position 1 (predicate) → predicates
  if (nonKeywordCount === 2) return "predicate";
  // Position 2+ (object) → both
  return "";
}

/**
 * Fetch entity suggestions from the backend, optionally filtered by type.
 * Caches the last query to avoid redundant network calls while typing.
 */
async function fetchEntities(query, entityType = "") {
  const now = Date.now();
  if (
    entityCache.query === query &&
    entityCache.type === entityType &&
    now - entityCache.timestamp < CACHE_TTL
  ) {
    return entityCache.results;
  }
  try {
    let url = `${AUTOCOMPLETE_ENDPOINT}?q=${encodeURIComponent(query)}&limit=10`;
    if (entityType) url += `&type=${entityType}`;
    const resp = await fetch(url);
    if (!resp.ok) return [];
    const data = await resp.json();
    const results = data.results || [];
    entityCache = { query, type: entityType, results, timestamp: now };
    return results;
  } catch {
    return [];
  }
}

/** Convert a backend entity result to a CodeMirror completion option. */
function entityToOption(entity) {
  const typeIcon = entity.type === "node" ? "●" : "◈";
  return {
    label: entity.id,
    type: entity.type === "node" ? "keyword" : "property",
    detail: `${typeIcon} ${entity.label}`,
    info: () => {
      const el = document.createElement("div");
      el.style.cssText = "padding:4px 8px;font-size:12px;line-height:1.5";
      el.innerHTML = `<strong>${entity.label}</strong><br><span style="color:#888;font-size:11px">${entity.iri}</span>`;
      return el;
    },
    apply: entity.iri,
  };
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

/**
 * CodeMirror language extension for SPARQL syntax highlighting.
 */
export function sparql() {
  return sql({
    dialect: SQLite,
    upperCaseKeywords: true,
    keywords: SPARQL_KEYWORDS,
  });
}

/**
 * Context-aware SPARQL autocomplete.
 *
 * Provides:
 *   - SPARQL keywords (SELECT, WHERE, PREFIX, etc.)
 *   - PREFIX declarations (`PREFIX rdf: <http://...>`)
 *   - Known prefix names (`rdf:`, `rdfs:`, `owl:`, etc.)
 *   - **Entity search** — suggests nodes and predicates from the store
 *     (Wikidata-style, matching partial IDs and labels)
 *
 * @param {Array<{prefix:string, uri:string}>} [extraPrefixes]
 * @returns {import("@codemirror/state").Extension}
 */
export function sparqlAutocomplete(extraPrefixes = []) {
  // Merge prefixes
  const allPrefixes = [...KNOWN_PREFIXES];
  for (const ep of extraPrefixes) {
    if (!allPrefixes.find((p) => p.prefix === ep.prefix)) {
      allPrefixes.push(ep);
    }
  }

  const prefOpts = prefixOptions(allPrefixes);
  const prefShort = prefixShortOptions(allPrefixes);

  return autocompletion({
    activateOnTyping: true,
    maxRenderedOptions: 15,
    override: [
      // ── Synchronous: keywords + prefixes ──────────────────────────
      (context) => {
        const word = context.matchBefore(/\w*/);
        if (!word || (word.from === word.to && !context.explicit)) return null;

        const prefix = word.text.toLowerCase();
        const options = [];

        // SPARQL keywords
        for (const opt of keywordOptions) {
          if (opt.label.toLowerCase().startsWith(prefix)) {
            options.push(opt);
          }
        }

        // After "PREFIX " → suggest prefix names
        const lineBefore = context.state.sliceDoc(
          Math.max(0, context.pos - 40),
          context.pos - word.from,
        );
        if (/PREFIX\s+$/i.test(lineBefore)) {
          for (const opt of prefShort) {
            if (opt.label.toLowerCase().startsWith(prefix)) {
              options.push(opt);
            }
          }
        }

        // Full PREFIX lines
        if (prefix.length >= 2 && options.length < 5) {
          for (const opt of prefOpts) {
            if (opt.label.toLowerCase().startsWith(prefix)) {
              options.push(opt);
            }
          }
        }

        if (options.length > 0) return { from: word.from, options };
        return null;
      },

      // ── Async: entity autocomplete (context-aware) ────────────────
      async (context) => {
        const word = context.matchBefore(/\w{2,}/);
        if (!word || word.text.length < 2) return null;

        const query = word.text;
        const entityType = guessPosition(context);
        const entities = await fetchEntities(query, entityType);
        if (entities.length === 0) return null;

        const options = entities.map(entityToOption);
        return { from: word.from, options };
      },
    ],
  });
}
