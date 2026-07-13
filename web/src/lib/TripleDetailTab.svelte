<script>
  /** Triple detail view — shows full info for a single triple. */

  import { tabStore } from "./tabStore.svelte.js";

  let { data = {} } = $props();
  let d = $derived(data || {});

  let triple = $derived(d.triple || {});
  let subject = $derived(d.subject || {});
  let predicate = $derived(d.predicate || {});
  let object = $derived(d.object || {});
  let subjLabel = $derived(d._subject_label || triple.subject_id || "");
  let predLabel = $derived(d._predicate_label || triple.predicate_id || "");
  let objLabel = $derived(d._object_label || (triple.object_type !== "uri" ? triple.object_value : triple.object_value) || "");

  function parseLabels(raw) {
    if (!raw) return null;
    if (typeof raw === "string") { try { raw = JSON.parse(raw); } catch { return null; } }
    if (raw && typeof raw === "object" && !Array.isArray(raw)) return raw;
    return null;
  }

  let subjLabels = $derived(parseLabels(subject.labels));
  let subjDefs = $derived(parseLabels(subject.definitions));
  let predLabels = $derived(parseLabels(predicate.labels));
  let predDescs = $derived(parseLabels(predicate.descriptions));
  let objLabels = $derived(triple.object_type === "uri" ? parseLabels(object.labels) : null);
  let objDefs = $derived(triple.object_type === "uri" ? parseLabels(object.definitions) : null);

  /** Render object value based on datatype */
  function renderObject() {
    if (triple.object_type !== "uri") {
      const dt = triple.object_datatype;
      if (dt === "text/katex") {
        return `<div class="katex-render">$$${triple.object_value}$$</div>`;
      }
      if (dt === "xsd:integer" || dt === "xsd:decimal") {
        return `<span class="literal-num">${triple.object_value}</span>`;
      }
      if (dt === "xsd:boolean") {
        return `<span class="literal-bool">${triple.object_value}</span>`;
      }
      if (triple.object_lang) {
        return `<span class="literal-lang" lang="${triple.object_lang}">${triple.object_value}</span>`;
      }
      return `<span class="literal-str">${triple.object_value}</span>`;
    }
    // URI — show as link
    return `<span class="literal-uri">${objLabel || triple.object_value}</span>`;
  }

  async function openNode(id) {
    if (!id) return;
    try {
      const resp = await fetch(`/api/v1/graph/nodes/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const node = result.node || result;
      const label = node.labels ? (parseLabels(node.labels)?.["en"] || id) : id;
      tabStore.open("status", label, { ...node, triples: result.triples || [] }, {
        idKey: `node-${id}`, replaceable: false,
      });
    } catch { /* silent */ }
  }

  async function openPredicate(id) {
    if (!id) return;
    try {
      const resp = await fetch(`/api/v1/graph/predicates/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const pred = result.predicate || result;
      const label = pred.labels ? (parseLabels(pred.labels)?.["en"] || id) : id;
      tabStore.open("status", label, { ...pred, triples: result.triples || [] }, {
        idKey: `pred-${id}`, replaceable: false,
      });
    } catch { /* silent */ }
  }

  function objEntries(dict) {
    if (!dict) return [];
    return Object.entries(dict);
  }
</script>

<div class="triple-detail">
  <!-- Full ID arc -->
  <div class="detail-header">
    <div class="arc-row">
      <span class="arc-ent" role="button" tabindex="-1"
        onclick={() => openNode(triple.subject_id)}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); openNode(triple.subject_id); } }}>
        {triple.subject_id}
      </span>
      <span class="arc-arrow">→</span>
      <span class="arc-ent" role="button" tabindex="-1"
        onclick={() => openPredicate(triple.predicate_id)}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); openPredicate(triple.predicate_id); } }}>
        {triple.predicate_id}
      </span>
      <span class="arc-arrow">→</span>
      <span class="arc-ent" role="button" tabindex="-1"
        onclick={() => { if (triple.object_type === "uri") openNode(triple.object_value); }}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (triple.object_type === "uri") openNode(triple.object_value); } }}>
        {triple.object_value}
      </span>
    </div>
    <div class="arc-labels">
      <span class="arc-label">{subjLabel}</span>
      <span class="arc-arrow">→</span>
      <span class="arc-label">{predLabel}</span>
      <span class="arc-arrow">→</span>
      <span class="arc-label">{objLabel}</span>
    </div>
  </div>

  <!-- Subject section -->
  <div class="section">
    <div class="section-title">
      <span class="ent-link" role="button" tabindex="-1"
        onclick={() => openNode(triple.subject_id)}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); openNode(triple.subject_id); } }}>
        Subject: {triple.subject_id}
      </span>
    </div>
    {#if subjLabels}
      <div class="sub-section">
        <span class="sub-label">Labels</span>
        {#each objEntries(subjLabels) as [lang, text]}
          <div class="lang-row">
            <span class="lang-code">{lang}</span>
            <span class="lang-val">{text}</span>
          </div>
        {/each}
      </div>
    {/if}
    {#if subjDefs}
      <div class="sub-section">
        <span class="sub-label">Definitions</span>
        {#each objEntries(subjDefs) as [lang, text]}
          <div class="lang-row">
            <span class="lang-code">{lang}</span>
            <span class="lang-val def">{text}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Predicate section -->
  <div class="section">
    <div class="section-title">
      <span class="ent-link" role="button" tabindex="-1"
        onclick={() => openPredicate(triple.predicate_id)}
        onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); openPredicate(triple.predicate_id); } }}>
        Predicate: {triple.predicate_id}
      </span>
    </div>
    {#if predLabels}
      <div class="sub-section">
        <span class="sub-label">Labels</span>
        {#each objEntries(predLabels) as [lang, text]}
          <div class="lang-row">
            <span class="lang-code">{lang}</span>
            <span class="lang-val">{text}</span>
          </div>
        {/each}
      </div>
    {/if}
    {#if predDescs}
      <div class="sub-section">
        <span class="sub-label">Descriptions</span>
        {#each objEntries(predDescs) as [lang, text]}
          <div class="lang-row">
            <span class="lang-code">{lang}</span>
            <span class="lang-val def">{text}</span>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Object section -->
  <div class="section">
    <div class="section-title">
      {#if triple.object_type === "uri"}
        <span class="ent-link" role="button" tabindex="-1"
          onclick={() => openNode(triple.object_value)}
          onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); openNode(triple.object_value); } }}>
          Object: {triple.object_value}
        </span>
      {:else}
        <span>Object: {triple.object_value}</span>
      {/if}
      {#if triple.object_datatype}
        <span class="dt-badge">{triple.object_datatype}</span>
      {/if}
      {#if triple.object_lang}
        <span class="dt-badge lang">{triple.object_lang}</span>
      {/if}
    </div>

    {#if triple.object_type !== "uri" && triple.object_datatype === "text/katex"}
      <div class="katex-preview">{triple.object_value}</div>
    {:else if triple.object_type === "uri"}
      {#if objLabels}
        <div class="sub-section">
          <span class="sub-label">Labels</span>
          {#each objEntries(objLabels) as [lang, text]}
            <div class="lang-row">
              <span class="lang-code">{lang}</span>
              <span class="lang-val">{text}</span>
            </div>
          {/each}
        </div>
      {/if}
      {#if objDefs}
        <div class="sub-section">
          <span class="sub-label">Definitions</span>
          {#each objEntries(objDefs) as [lang, text]}
            <div class="lang-row">
              <span class="lang-code">{lang}</span>
              <span class="lang-val def">{text}</span>
            </div>
          {/each}
        </div>
      {/if}
    {:else}
      <div class="literal-display">{@html renderObject()}</div>
    {/if}
  </div>

  {#if triple.created_at}
    <div class="footer-meta">
      <span class="meta-item">Created: {triple.created_at}</span>
    </div>
  {/if}
</div>

<style>
  .triple-detail { font-family: monospace; font-size: 0.85rem; height: 100%; overflow-y: auto; padding: 0; }
  .detail-header { padding: 0.75rem; border-bottom: 1px solid #2a2a3e; display: flex; flex-direction: column; gap: 0.35rem; }
  .arc-row { display: flex; align-items: center; gap: 0.25rem; font-size: 0.95rem; font-weight: 700; }
  .arc-labels { display: flex; align-items: center; gap: 0.25rem; font-size: 0.82rem; color: #c0c0d0; }
  .arc-arrow { color: var(--clr-dim); flex-shrink: 0; }
  .arc-ent { cursor: pointer; color: #7cf; transition: background 0.1s; padding: 0 2px; border-radius: 2px; }
  .arc-ent:hover { background: rgba(255,255,255,0.08); text-decoration: underline; }
  .arc-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .section { padding: 0.5rem 0.75rem; border-bottom: 1px solid #2a2a3e; }
  .section:last-of-type { border-bottom: none; }
  .section-title { font-size: 0.85rem; font-weight: 600; color: #e0e0e0; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.5rem; }
  .ent-link { cursor: pointer; color: #7cf; transition: background 0.1s; }
  .ent-link:hover { background: rgba(255,255,255,0.08); text-decoration: underline; }
  .sub-section { margin: 0.3rem 0 0.3rem 0.5rem; }
  .sub-label { font-size: 0.72rem; color: var(--clr-sub); text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 0.15rem; }
  .lang-row { display: flex; gap: 0.5rem; padding: 0.1rem 0; align-items: baseline; }
  .lang-code { color: var(--clr-sub); font-size: 0.72rem; min-width: 2.5rem; text-transform: uppercase; }
  .lang-val { color: #e0e0e0; font-size: 0.85rem; }
  .lang-val.def { color: var(--clr-sub); font-style: italic; }
  .dt-badge { font-size: 0.65rem; padding: 1px 5px; border-radius: 3px; background: #2a2a4a; color: var(--clr-sub); text-transform: uppercase; }
  .dt-badge.lang { background: #2a3a2a; color: #7f7; }
  .literal-display { padding: 0.3rem 0.5rem; background: #111; border: 1px solid #333; border-radius: 4px; color: #e0e0e0; font-size: 0.85rem; }
  .katex-preview { padding: 0.3rem 0.5rem; background: #111; border: 1px solid #333; border-radius: 4px; color: #a0d0a0; font-family: monospace; font-size: 0.85rem; }
  .footer-meta { padding: 0.4rem 0.75rem; font-size: 0.72rem; color: var(--clr-dim); border-top: 1px solid #2a2a3e; }
  .meta-item { margin-right: 1rem; }
</style>
