<script>
  /**
   * SPARQL result table — renders SELECT/ASK/CONSTRUCT results.
   *
   * Props:
   *   result: A SPARQL JSON results object (or null/undefined).
   *
   * Handles:
   *   - SELECT: table with columns from head.vars
   *   - ASK: big Yes/No display
   *   - CONSTRUCT/DESCRIBE: Turtle textarea
   *   - Empty/null: nothing rendered
   */

  import { tabStore } from "../tabStore.svelte.js";
  import { getLocale } from "../userConfig.svelte.js";
  import { getLabel } from "../listTabFormat.js";
  import { sparqlStore } from "./sparqlStore.svelte.js";

  /** @type {import("@lightercore/ui/types").SparqlResult|null} */
  let { result } = $props();

  /** @type {number|null} */
  let selectedRowIndex = $state(null);

  // ── Column sort mode ──────────────────────────────────────────────────
  const STORAGE_KEY = "semantika:sparql-sort-mode";

  /** @type {"query"|"alpha"} */
  let sortMode = $state(localStorage.getItem(STORAGE_KEY) || "query");

  $effect(() => {
    selectedRowIndex = null;
  });

  function isSelect(r) {
    return r && r.results && r.results.bindings;
  }

  function isAsk(r) {
    return r && "boolean" in r;
  }

  function isConstruct(r) {
    return r && r.data && r.format;
  }

  function rawVars(r) {
    return r.head?.vars || [];
  }

  function bindings(r) {
    return r.results?.bindings || [];
  }

  /**
   * Extract ?var names in first-appearance order from a SPARQL query.
   * Mirrors the backend _extract_var_order helper.
   */
  function extractVarOrder(query) {
    const re = /(?<![?])\?([a-zA-Z_][a-zA-Z0-9_]*)/g;
    const seen = new Set();
    const order = [];
    let m;
    while ((m = re.exec(query)) !== null) {
      if (!seen.has(m[1])) {
        seen.add(m[1]);
        order.push(m[1]);
      }
    }
    return order;
  }

  /**
   * Get the displayed variable list, sorted per current sortMode.
   */
  function sortedVars(r) {
    const raw = rawVars(r);
    if (sortMode === "query" && sparqlStore.query) {
      const desired = extractVarOrder(sparqlStore.query)
        .filter((v) => raw.includes(v));
      if (desired.length > 0) return desired;
    }
    // fallback: alphabetical
    return [...raw].sort();
  }

  function toggleSortMode() {
    sortMode = sortMode === "query" ? "alpha" : "query";
    localStorage.setItem(STORAGE_KEY, sortMode);
  }

  // ── URI ↔ internal ID (mirrors backend _from_uri) ────────────────────
  const BASE_URI = "https://semantika.local/";
  const KNOWN_PREFIXES = {
    rdf: "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    rdfs: "http://www.w3.org/2000/01/rdf-schema#",
    xsd: "http://www.w3.org/2001/XMLSchema#",
    owl: "http://www.w3.org/2002/07/owl#",
  };

  /** Convert a SPARQL result IRI back to an internal Semantika ID. */
  function fromUri(uri) {
    for (const [prefix, ns] of Object.entries(KNOWN_PREFIXES)) {
      if (uri.startsWith(ns)) {
        const local = uri.slice(ns.length);
        if (local) return `${prefix}:${local}`;
      }
    }
    const nodeNs = `${BASE_URI}node/`;
    if (uri.startsWith(nodeNs)) return uri.slice(nodeNs.length);
    const resNs = `${BASE_URI}resource/`;
    if (uri.startsWith(resNs)) return uri.slice(resNs.length);
    // External URI — pass through
    return uri;
  }

  /** Guess whether an internal ID refers to a node or a predicate. */
  function guessIdType(id) {
    // Known-prefix IDs (rdf:, rdfs:, xsd:, owl:) are predicates
    for (const prefix of Object.keys(KNOWN_PREFIXES)) {
      if (id.startsWith(`${prefix}:`)) return "predicate";
    }
    // resource/ namespace + colon → predicate (e.g. rs:opcion)
    if (id.includes(":")) return "predicate";
    // node/ namespace or bare → node
    return "node";
  }

  /** Open a view tab for a URI result entry. */
  async function openEntityView(entry) {
    if (!entry || entry.type !== "uri") return;
    const internalId = fromUri(entry.value);
    if (internalId === entry.value && (internalId.startsWith("http://") || internalId.startsWith("https://"))) {
      return; // external URI, can't look up
    }
    const idType = guessIdType(internalId);
    try {
      const endpoint = idType === "node" ? "nodes" : "predicates";
      const resp = await fetch(`/api/v1/graph/${endpoint}/${encodeURIComponent(internalId)}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const entity = result.node || result.predicate || result;
      const label = getLabel(entity?.labels, getLocale()) || internalId;
      tabStore.open("status", label, { ...entity, triples: result.triples || [] }, {
        idKey: `${idType}-${internalId}`, replaceable: false,
      });
    } catch { /* silent */ }
  }

  /** Short human-readable label for a literal's datatype or language. */
  function literalTypeLabel(entry) {
    if (entry["xml:lang"]) return `@${entry["xml:lang"]}`;
    if (entry.datatype) {
      const dt = entry.datatype.value || entry.datatype;
      // Strip namespace to short name
      const short = dt.includes("#") ? dt.split("#").pop() : dt.includes("/") ? dt.split("/").pop() : dt;
      return short === "string" ? "" : short;
    }
    return "";
  }

  function cellValue(binding, varName) {
    const entry = binding[varName];
    if (!entry) return "";
    if (entry.type === "uri") return entry._label || entry.value;
    if (entry.type === "literal") return entry.value;
    if (entry.type === "bnode") return `_:${entry.value}`;
    return entry.value || "";
  }

  function cellType(binding, varName) {
    const entry = binding[varName];
    if (!entry) return "";
    if (entry.type === "uri") return entry._label ? "uri-rich" : "uri";
    if (entry.type === "literal") return literalTypeLabel(entry) ? "literal-rich" : "literal";
    return entry.type || "";
  }

  function cellSubValue(binding, varName) {
    const entry = binding[varName];
    if (!entry) return "";
    if (entry.type === "uri") return entry.value; // full IRI below label
    if (entry.type === "literal") return literalTypeLabel(entry);
    return "";
  }

  function cellTooltip(binding, varName) {
    const entry = binding[varName];
    if (!entry) return "";
    if (entry.type === "uri") return entry.value;
    if (entry.type === "literal") {
      let tip = entry.value;
      if (entry.datatype) tip += `\nDatatype: ${entry.datatype.value}`;
      return tip;
    }
    return "";
  }

  function handleRowClick(index) {
    if (selectedRowIndex === index) {
      selectedRowIndex = null;
    } else {
      selectedRowIndex = index;
    }
  }

  /**
   * Copy SPARQL results as JSON to clipboard.
   */
  function copyAsJson() {
    if (!result) return;
    navigator.clipboard.writeText(JSON.stringify(result, null, 2));
  }

  /**
   * Export bindings as CSV.
   */
  function exportCsv() {
    if (!isSelect(result)) return;
    const v = sortedVars(result);
    const rows = bindings(result);
    const header = v.join(",");
    const data = rows.map((row) =>
      v.map((col) => {
        const val = cellValue(row, col);
        // Quote if contains comma or quotes
        if (val.includes(",") || val.includes('"') || val.includes("\n")) {
          return `"${val.replace(/"/g, '""')}"`;
        }
        return val;
      }).join(","),
    );
    const csv = [header, ...data].join("\n");
    navigator.clipboard.writeText(csv);
  }
</script>

<div class="result-area">
  {#if !result}
    <div class="placeholder">
      <p>Run a query to see results.</p>
    </div>

  {:else if isAsk(result)}
    <div class="ask-result">
      <span class="ask-icon" class:yes={result.boolean} class:no={!result.boolean}>
        {result.boolean ? "✔" : "✘"}
      </span>
      <span class="ask-text">{result.boolean ? "Yes" : "No"}</span>
    </div>

  {:else if isConstruct(result)}
    <div class="construct-result">
      <div class="construct-header">
        <span class="construct-label">Turtle ({result.format})</span>
        <button class="btn-icon" onclick={copyAsJson} title="Copy as JSON">📋</button>
      </div>
      <textarea class="turtle-output" readonly rows="12"
        >{result.data}</textarea>
    </div>

  {:else if isSelect(result)}
    {@const v = sortedVars(result)}
    {@const rows = bindings(result)}
    <div class="select-result">
      <div class="result-header">
        <span class="result-count">{rows.length} row{rows.length !== 1 ? "s" : ""}</span>
        <div class="result-actions">
          <button class="btn-icon" onclick={exportCsv} title="Export CSV">📄</button>
          <button class="btn-icon" onclick={copyAsJson} title="Copy as JSON">📋</button>
          <button
            class="btn-icon btn-sort"
            onclick={toggleSortMode}
            title={sortMode === "query" ? "Columns: query order" : "Columns: alphabetical"}
          >{sortMode === "query" ? "⇕Q" : "⇕A"}</button>
        </div>
      </div>

      {#if rows.length === 0}
        <p class="empty">No results.</p>
      {:else}
        <div class="table-wrapper">
          <table class="result-table">
            <thead>
              <tr>
                <th class="row-num">#</th>
                {#each v as col}
                  <th class="col-{col}">
                    <span class="col-name">{col}</span>
                    <span class="col-type-badge">?</span>
                  </th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each rows as row, i}
                <tr
                  class="result-row"
                  class:selected={selectedRowIndex === i}
                  onclick={() => handleRowClick(i)}
                  role="button"
                  tabindex="0"
                  onkeydown={(e) => { if (e.key === "Enter") handleRowClick(i); }}
                >
                  <td class="row-num">{i + 1}</td>
                  {#each v as col}
                    {@const ct = cellType(row, col)}
                    {@const entry = row[col]}
                    <td
                      class="cell cell-{ct}"
                      class:cell-clickable={ct === "uri" || ct === "uri-rich"}
                      title={cellTooltip(row, col)}
                      onclick={ct === "uri" || ct === "uri-rich" ? () => openEntityView(entry) : undefined}
                      role={ct === "uri" || ct === "uri-rich" ? "button" : undefined}
                      tabindex={ct === "uri" || ct === "uri-rich" ? "0" : undefined}
                      onkeydown={ct === "uri" || ct === "uri-rich" ? (e) => { if (e.key === "Enter") openEntityView(entry); } : undefined}
                    >
                      {#if ct === "uri-rich"}
                        <span class="uri-label">{cellValue(row, col)}</span>
                        <span class="cell-sub">{cellSubValue(row, col)}</span>
                      {:else if ct === "literal-rich"}
                        <span class="literal-value">{cellValue(row, col)}</span>
                        <span class="cell-sub">{cellSubValue(row, col)}</span>
                      {:else}
                        {cellValue(row, col)}
                      {/if}
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>

  {:else}
    <div class="unknown-result">
      <pre>{JSON.stringify(result, null, 2)}</pre>
    </div>
  {/if}
</div>

<style>
  .result-area {
    flex: 1;
    overflow: auto;
    padding: 0;
  }

  .placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--clr-dim, #888);
    font-style: italic;
  }

  .ask-result {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    padding: 48px 16px;
    gap: 12px;
  }

  .ask-icon {
    font-size: 64px;
    line-height: 1;
  }
  .ask-icon.yes { color: #4caf50; }
  .ask-icon.no { color: #f44336; }

  .ask-text {
    font-size: 24px;
    font-weight: 600;
  }

  .construct-result {
    padding: 12px 16px;
  }

  .construct-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .construct-label {
    font-size: 12px;
    color: var(--clr-muted, #888);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .turtle-output {
    width: 100%;
    min-height: 200px;
    background: #111;
    color: #e0e0e0;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 8px;
    font-family: "SF Mono", "Fira Code", "Fira Mono", monospace;
    font-size: 12px;
    resize: vertical;
  }

  .select-result {
    display: flex;
    flex-direction: column;
    height: 100%;
  }

  .result-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: rgba(255, 255, 255, 0.03);
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }

  .result-count {
    font-size: 12px;
    color: var(--clr-muted, #888);
  }

  .result-actions {
    display: flex;
    gap: 4px;
  }

  .btn-icon {
    background: none;
    border: 1px solid #444;
    border-radius: 4px;
    color: #ccc;
    cursor: pointer;
    font-size: 14px;
    padding: 2px 6px;
    line-height: 1.4;
  }
  .btn-icon:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: #666;
  }

  .btn-sort {
    font-size: 12px;
    font-weight: 600;
    padding: 2px 5px;
    letter-spacing: 0.3px;
  }
  .btn-sort:hover {
    border-color: #7ec8e3;
    color: #7ec8e3;
  }

  .table-wrapper {
    overflow: auto;
    flex: 1;
  }

  .result-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }

  .result-table thead {
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .result-table th {
    background: #222;
    color: #aaa;
    text-align: left;
    padding: 6px 10px;
    border-bottom: 2px solid #333;
    font-weight: 500;
    white-space: nowrap;
  }

  .result-table td {
    padding: 5px 10px;
    border-bottom: 1px solid #2a2a2a;
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .result-row {
    cursor: default;
  }
  .result-row:hover td {
    background: rgba(255, 255, 255, 0.03);
  }
  .result-row.selected td {
    background: rgba(100, 100, 180, 0.12);
  }

  .row-num {
    width: 32px;
    min-width: 32px;
    color: var(--clr-dim, #555);
    text-align: right;
    font-size: 11px;
    padding-right: 6px;
  }

  .cell-uri {
    color: #7ec8e3;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 12px;
  }

  .cell-clickable {
    cursor: pointer;
  }
  .cell-clickable:hover {
    background: rgba(126, 200, 227, 0.08);
  }

  .cell-uri-rich {
    padding: 2px 10px;
    line-height: 1.5;
  }
  .cell-uri-rich .uri-label {
    display: block;
    color: #e0e0e0;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .cell-literal {
    color: #ce9178;
  }

  .cell-literal-rich {
    padding: 2px 10px;
    line-height: 1.5;
  }
  .cell-literal-rich .literal-value {
    display: block;
    color: #ce9178;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /** Shared secondary line (full IRI for URIs, datatype/lang for literals). */
  .cell-sub {
    display: block;
    color: #7ec8e3;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 11px;
    opacity: 0.7;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .cell-literal-rich .cell-sub {
    color: #888;
    font-family: inherit;
  }

  .cell-bnode {
    color: #569cd6;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 12px;
  }

  .col-name {
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 12px;
  }

  .col-type-badge {
    font-size: 10px;
    opacity: 0.5;
    margin-left: 2px;
  }

  .empty {
    padding: 24px 16px;
    color: var(--clr-dim, #888);
    text-align: center;
  }

  .unknown-result {
    padding: 12px 16px;
  }
  .unknown-result pre {
    background: #111;
    padding: 8px;
    border-radius: 4px;
    font-size: 12px;
    overflow: auto;
  }
</style>
