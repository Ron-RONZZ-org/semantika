<script>
  let { data = {} } = $props();
  let d = $derived(data || {});

  function renderValue(val) {
    if (val === null || val === undefined) return "";
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  }
</script>

<div class="status">
  {#if d.type === "table" && Array.isArray(d.data)}
    {#if d.data.length > 0}
      <table>
        <thead><tr>{#each Object.keys(d.data[0]).filter(k => !k.startsWith("_")) as col}<th>{col}</th>{/each}</tr></thead>
        <tbody>
          {#each d.data as row}
            <tr>{#each Object.entries(row) as [key, val]}{#if !key.startsWith("_")}<td>{renderValue(val)}</td>{/if}{/each}</tr>
          {/each}
        </tbody>
      </table>
    {:else}
      <p class="empty">No results.</p>
    {/if}
  {:else if d.nodes !== undefined}
    <div class="section-header">
      <h3 class="title">Nodes ({d.nodes.length})</h3>
    </div>
    {#each d.nodes as node}
      <div class="row">
        <span class="key">{node.node_id?.slice(0, 12) || ""}</span>
        <span class="val">{node.label || node.node_id || ""}</span>
      </div>
    {:else}
      <p class="empty">No nodes.</p>
    {/each}
  {:else if d.predicates !== undefined}
    <div class="section-header">
      <h3 class="title">Predicates ({d.predicates.length})</h3>
    </div>
    {#each d.predicates as pred}
      <div class="row">
        <span class="key">{pred.predicate_id?.slice(0, 12) || ""}</span>
        <span class="val">{pred.label || pred.predicate_id || ""}</span>
      </div>
    {:else}
      <p class="empty">No predicates.</p>
    {/each}
  {:else if d.triples !== undefined}
    <div class="section-header">
      <h3 class="title">Triples ({d.triples.length})</h3>
    </div>
    {#each d.triples as triple}
      <div class="row">
        <span class="key">{triple.subject_id?.slice(0, 8) || ""}</span>
        <span class="val">{triple.predicate_id || ""} → {triple.object_value?.slice(0, 24) || ""}</span>
      </div>
    {:else}
      <p class="empty">No triples.</p>
    {/each}
  {:else if d.reply}
    <div class="message">{d.reply}</div>
  {:else if d.message}
    <p class="message">{d.message}</p>
  {:else if d.status}
    <p class="message">{d.status}</p>
  {:else if d.removed}
    <p class="message">Removed: {d.removed.join(", ")}</p>
  {:else if d.done}
    <p class="message">Done: {d.done.join(", ")}</p>
  {:else if d._summary}
    <p class="message" style="white-space:pre-wrap">{d._summary}</p>
  {:else if d.uuid}
    <div class="row">
      <span class="key">{d.uuid?.slice(0, 8) || ""}</span>
      <span class="val">{d.title || d.label || d.node_id || d.predicate_id || ""}</span>
    </div>
  {:else if d.title}
    <p class="message">{d.title}</p>
  {:else}
    {#each Object.entries(d) as [key, val]}
      {#if typeof val === "string" && val}
        <div class="row">
          <span class="key">{key}</span>
          <span class="val">{val}</span>
        </div>
      {:else if typeof val === "number"}
        <div class="row">
          <span class="key">{key}</span>
          <span class="val">{val}</span>
        </div>
      {:else if typeof val === "boolean"}
        <div class="row">
          <span class="key">{key}</span>
          <span class="val">{val ? "✓" : "—"}</span>
        </div>
      {:else if Array.isArray(val) && val.length > 0}
        <div class="row">
          <span class="key">{key}</span>
          <span class="val">{val.length} item{val.length !== 1 ? "s" : ""}</span>
        </div>
      {/if}
    {/each}
    {#if Object.keys(d).length === 0}
      <p class="message">No data.</p>
    {/if}
  {/if}
</div>

<style>
  .status {
    font-family: monospace;
    font-size: 0.85rem;
    height: 100%;
    overflow-y: auto;
  }
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
    padding: 0.75rem 0.75rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
  }
  .title {
    font-size: 0.95rem;
    color: #e0e0e0;
    font-weight: 600;
  }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { padding: 0.3rem 0.5rem; border: 1px solid #333; text-align: left; }
  th { background: #222; color: #c0c0c0; font-weight: 600; }
  td { color: #e0e0e0; }
  .row {
    display: flex;
    gap: 0.5rem;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid #2a2a3e;
    align-items: center;
  }
  .row:last-child { border-bottom: none; }
  .key {
    color: var(--clr-sub);
    min-width: 5rem;
  }
  .val {
    color: #e0e0e0;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
  .message {
    color: #e0e0e0;
    white-space: pre-wrap;
    padding: 0.75rem;
  }
</style>
