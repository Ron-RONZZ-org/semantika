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

  /** @type {import("@lightercore/ui/types").SparqlResult|null} */
  let { result } = $props();

  /** @type {number|null} */
  let selectedRowIndex = $state(null);

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

  function vars(r) {
    return r.head?.vars || [];
  }

  function bindings(r) {
    return r.results?.bindings || [];
  }

  function cellValue(binding, varName) {
    const entry = binding[varName];
    if (!entry) return "";
    if (entry.type === "uri") return entry._label || entry.value;
    if (entry.type === "literal") {
      let val = entry.value;
      if (entry["xml:lang"]) val += `@${entry["xml:lang"]}`;
      if (entry.datatype) val += ` (${entry.datatype.value})`;
      return val;
    }
    if (entry.type === "bnode") return `_:${entry.value}`;
    return entry.value || "";
  }

  function cellType(binding, varName) {
    const entry = binding[varName];
    if (!entry) return "";
    if (entry.type === "uri") return entry._label ? "uri-rich" : "uri";
    return entry.type || "";
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
    const v = vars(result);
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
    {@const v = vars(result)}
    {@const rows = bindings(result)}
    <div class="select-result">
      <div class="result-header">
        <span class="result-count">{rows.length} row{rows.length !== 1 ? "s" : ""}</span>
        <div class="result-actions">
          <button class="btn-icon" onclick={copyAsJson} title="Copy as JSON">📋</button>
          <button class="btn-icon" onclick={exportCsv} title="Export CSV">📄</button>
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
                    <td
                      class="cell cell-{cellType(row, col)}"
                      title={cellTooltip(row, col)}
                    >
                      {#if cellType(row, col) === "uri-rich"}
                        <span class="uri-label">{cellValue(row, col)}</span>
                        <span class="uri-value">{row[col]?.value || ""}</span>
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

  .cell-uri-rich {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 2px 0;
  }

  .uri-label {
    color: #e0e0e0;
    font-weight: 500;
  }

  .uri-value {
    color: #7ec8e3;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 11px;
    opacity: 0.7;
  }

  .cell-literal {
    color: #ce9178;
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
