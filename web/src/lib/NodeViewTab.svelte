<script>
  /** Rich viewer for nodes with built-in types — photo, video, document, code.
   *
   * Shows media/rendered content at the top, then a table of all triples below. */

  import { tabStore } from "./tabStore.svelte.js";

  let { data = {} } = $props();

  let node = $derived(data?.data || data);
  let nodeId = $derived(node?.node_id || "");
  let nodeType = $derived(node?.node_type || "");
  let fileUrl = $derived(node?.file_url || "");
  let filePath = $derived(node?.file_path || "");
  let triples = $derived(node?.triples || []);

  // Labels
  let labels = $derived.by(() => {
    if (!node?.labels) return {};
    try {
      return typeof node.labels === "string" ? JSON.parse(node.labels) : node.labels;
    } catch { return { en: node.labels }; }
  });
  let label = $derived(labels?.en || labels?.eo || labels?.fr || nodeId);
  let definitions = $derived.by(() => {
    if (!node?.definitions) return {};
    try {
      return typeof node.definitions === "string" ? JSON.parse(node.definitions) : node.definitions;
    } catch { return {}; }
  });
  let definition = $derived(definitions?.en || "");

  // Key metadata from triples
  let programmingLanguage = $derived.by(() => {
    for (const t of triples) { if (t.predicate_id === "sm:programmingLanguage") return t.object_value; }
    return "";
  });
  let dimension = $derived.by(() => {
    for (const t of triples) { if (t.predicate_id === "sm:dimension") return t.object_value; }
    return "";
  });
  let canonicalLink = $derived.by(() => {
    for (const t of triples) { if (t.predicate_id === "sm:canonicalLink") return t.object_value; }
    return "";
  });
  let fileSize = $derived.by(() => {
    for (const t of triples) { if (t.predicate_id === ":hasFileSize") return t.object_value; }
    return "";
  });
  let fileMime = $derived.by(() => {
    for (const t of triples) { if (t.predicate_id === ":hasFileMime") return t.object_value; }
    return "";
  });
  let mimeCategory = $derived.by(() => {
    const m = fileMime || "";
    if (m.startsWith("image/")) return "image";
    if (m.startsWith("video/")) return "video";
    if (m.startsWith("text/") || m === "application/json" || m === "application/xml"
        || m === "application/javascript") return "text";
    return "other";
  });

  // Code content
  let codeContent = $state("");
  let codeLoading = $state(false);
  let codeError = $state("");
  let codeCopied = $state(false);

  $effect(() => {
    if ((nodeType === "code" || nodeType === "document") && nodeId && !codeContent && !codeLoading) {
      loadCodeContent();
    }
  });

  function openTripleView() {
    tabStore.open("status", label, { ...node, triples }, {
      idKey: `node-${nodeId}`, replaceable: false,
    });
  }

  async function loadCodeContent() {
    if (codeContent || codeLoading || codeError) return;
    codeLoading = true;
    codeError = "";
    try {
      const resp = await fetch(`/api/v1/files/${encodeURIComponent(nodeId)}/content`);
      if (!resp.ok) {
        const err = await resp.text().catch(() => "");
        throw new Error(err || `HTTP ${resp.status}`);
      }
      codeContent = await resp.text();
    } catch (err) {
      codeError = `Failed to load code: ${err.message}`;
    } finally {
      codeLoading = false;
    }
  }

  async function copyCode() {
    if (!codeContent) return;
    try {
      await navigator.clipboard.writeText(codeContent);
      codeCopied = true;
      setTimeout(() => { codeCopied = false; }, 2000);
    } catch { /* clipboard API may fail */ }
  }

  function formatSize(bytes) {
    if (!bytes) return "";
    const n = parseInt(bytes, 10);
    if (isNaN(n)) return bytes;
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  }

  function tripleObjectLabel(t) {
    if (t.object_type === "uri") return `→ ${t.object_value}`;
    const val = t.object_value || "";
    if (t.object_datatype) return `${val} (${t.object_datatype})`;
    if (t.object_lang) return `${val}@${t.object_lang}`;
    return `"${val}"`;
  }
</script>

<div class="node-view">
  <!-- Header -->
  <div class="nv-header">
    <div class="nv-title">{label}</div>
    <div class="nv-id">{nodeId}</div>
    {#if definition}
      <div class="nv-definition">{definition}</div>
    {/if}
  </div>

  <!-- Badge bar -->
  <div class="nv-meta">
    {#if nodeType}
      <span class="nv-badge nv-badge-{nodeType}">{nodeType}</span>
    {/if}
    {#if programmingLanguage}
      <span class="nv-badge nv-lang">{programmingLanguage}</span>
    {/if}
    {#if dimension}
      <span class="nv-meta-item">{dimension}</span>
    {/if}
    {#if fileSize}
      <span class="nv-meta-item">{formatSize(fileSize)}</span>
    {/if}
    {#if fileMime}
      <span class="nv-meta-item">{fileMime}</span>
    {/if}
  </div>

  <!-- Media content -->
  {#if nodeType === "photo"}
    <div class="nv-media">
      <img src={fileUrl} alt={label} class="nv-image"
        onerror={(e) => { e.target.alt = 'Failed to load image'; }} />
    </div>
  {/if}

  {#if nodeType === "video"}
    <div class="nv-media">
      <video controls class="nv-video" preload="metadata">
        <source src={fileUrl} type={fileMime || "video/mp4"} />
        Your browser does not support video playback.
      </video>
    </div>
  {/if}

  {#if nodeType === "document"}
    <div class="nv-file-area">
      <div class="nv-file-icon">📄</div>
      <a href={fileUrl} class="nv-download-link" download={filePath.split("/").pop() || "file"}>
        ⬇ Download {filePath.split("/").pop() || "file"}
      </a>
      {#if mimeCategory === "text"}
        <button class="nv-view-text-btn" onclick={loadCodeContent}>
          {codeContent ? "Hide content" : "View content"}
        </button>
      {/if}
    </div>
    {#if codeLoading}
      <div class="nv-loading">Loading content…</div>
    {:else if codeError}
      <div class="nv-error">{codeError}</div>
    {:else if codeContent}
      <div class="nv-code-block">
        <div class="nv-code-header">
          <span class="nv-code-filename">{filePath.split("/").pop()}</span>
          <button class="nv-copy-btn" onclick={copyCode}>
            {codeCopied ? "✓ Copied" : "📋 Copy"}
          </button>
        </div>
        <pre class="nv-code-pre"><code>{codeContent}</code></pre>
      </div>
    {/if}
  {/if}

  {#if nodeType === "code"}
    <div class="nv-code-area">
      {#if codeLoading}
        <div class="nv-loading">Loading code…</div>
      {:else if codeError}
        <div class="nv-error">{codeError}</div>
      {:else if codeContent}
        <div class="nv-code-block">
          <div class="nv-code-header">
            <span class="nv-code-filename">{filePath.split("/").pop() || "source"}</span>
            <button class="nv-copy-btn" onclick={copyCode}>
              {codeCopied ? "✓ Copied" : "📋 Copy"}
            </button>
          </div>
          <pre class="nv-code-pre"><code>{codeContent}</code></pre>
        </div>
      {:else}
        <div class="nv-loading">Preparing…</div>
      {/if}
    </div>
  {/if}

  <!-- Canonical link -->
  {#if canonicalLink}
    <div class="nv-canonical">
      <a href={canonicalLink} target="_blank" rel="noopener noreferrer">🔗 {canonicalLink}</a>
    </div>
  {/if}

  <!-- Triples table -->
  <div class="nv-triples-section">
    <div class="nv-section-title">
      <span>Triples ({triples.length})</span>
      <button class="nv-raw-btn" onclick={openTripleView}>📋 View raw</button>
    </div>
    {#each triples as t}
      <div class="nv-triple-row">
        <span class="nv-triple-pred">{t.predicate_id}</span>
        <span class="nv-triple-obj">{tripleObjectLabel(t)}</span>
      </div>
    {:else}
      <div class="nv-triple-empty">No triples.</div>
    {/each}
  </div>
</div>

<style>
  .node-view { display: flex; flex-direction: column; height: 100%; overflow-y: auto; font-family: monospace; font-size: 0.85rem; padding: 1rem; gap: 0.75rem; }
  .nv-header { display: flex; flex-direction: column; gap: 2px; }
  .nv-title { font-size: 1.1rem; font-weight: 700; color: #e0e0e0; }
  .nv-id { font-size: 0.78rem; color: var(--clr-sub); }
  .nv-definition { font-size: 0.82rem; color: #b0b0b0; line-height: 1.4; }
  .nv-meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .nv-badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .nv-badge-photo { background: #1a3a2a; color: #6fcf97; border: 1px solid #2a5a3a; }
  .nv-badge-video { background: #1a2a3a; color: #6fc0cf; border: 1px solid #2a4a5a; }
  .nv-badge-document { background: #2a2a1a; color: #cfc06f; border: 1px solid #4a4a2a; }
  .nv-badge-code { background: #2a1a2a; color: #cf6fcf; border: 1px solid #4a2a4a; }
  .nv-lang { background: #1a2a1a; color: #6fcf6f; border: 1px solid #2a4a2a; }
  .nv-meta-item { font-size: 0.75rem; color: var(--clr-sub); }
  .nv-media { display: flex; justify-content: center; background: #1a1a2e; border: 1px solid #2a2a3e; border-radius: 6px; padding: 0.5rem; overflow: hidden; }
  .nv-image { max-width: 100%; max-height: 50vh; object-fit: contain; border-radius: 4px; }
  .nv-video { max-width: 100%; max-height: 50vh; border-radius: 4px; }
  .nv-file-area { display: flex; flex-direction: column; gap: 8px; align-items: center; padding: 1.5rem; background: #1a1a2e; border: 1px solid #2a2a3e; border-radius: 6px; }
  .nv-file-icon { font-size: 2.5rem; }
  .nv-download-link { display: inline-flex; align-items: center; gap: 6px; padding: 0.5rem 1rem; background: #2a2a4e; border: 1px solid #444; border-radius: 4px; color: #6fc0cf; text-decoration: none; font-size: 0.85rem; }
  .nv-download-link:hover { background: #3a3a5e; }
  .nv-view-text-btn { padding: 0.3rem 0.75rem; background: #2a2a3e; border: 1px solid #444; border-radius: 3px; color: #e0e0e0; cursor: pointer; font-family: monospace; font-size: 0.78rem; }
  .nv-view-text-btn:hover { background: #3a3a4e; }
  .nv-code-area { display: flex; flex-direction: column; gap: 4px; }
  .nv-code-block { border: 1px solid #2a2a3e; border-radius: 6px; overflow: hidden; background: #12121e; }
  .nv-code-header { display: flex; justify-content: space-between; align-items: center; padding: 0.4rem 0.75rem; background: #1a1a2e; border-bottom: 1px solid #2a2a3e; font-size: 0.75rem; }
  .nv-code-filename { color: var(--clr-sub); }
  .nv-copy-btn { padding: 0.15rem 0.5rem; background: #2a2a3e; border: 1px solid #444; border-radius: 3px; color: #e0e0e0; cursor: pointer; font-family: monospace; font-size: 0.72rem; }
  .nv-copy-btn:hover { background: #3a3a4e; }
  .nv-code-pre { padding: 0.75rem; margin: 0; overflow-x: auto; overflow-y: auto; max-height: 60vh; }
  .nv-code-pre code { color: #c0c0c0; font-family: monospace; font-size: 0.78rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
  .nv-canonical { padding: 0.5rem; background: #1a1a2e; border: 1px solid #2a2a3e; border-radius: 4px; font-size: 0.78rem; }
  .nv-canonical a { color: #6fc0cf; text-decoration: none; word-break: break-all; }
  .nv-canonical a:hover { text-decoration: underline; }
  .nv-loading { color: var(--clr-sub); text-align: center; padding: 1rem; }
  .nv-error { color: #f77; background: #2a1a1a; border: 1px solid #a33; border-radius: 4px; padding: 0.5rem 0.75rem; font-size: 0.78rem; }
  /* Triples section */
  .nv-triples-section { border-top: 1px solid #2a2a3e; padding-top: 0.5rem; }
  .nv-section-title { display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; font-weight: 600; color: var(--clr-sub); margin-bottom: 0.4rem; }
  .nv-raw-btn { padding: 0.15rem 0.5rem; background: #2a2a3e; border: 1px solid #444; border-radius: 3px; color: var(--clr-sub); cursor: pointer; font-family: monospace; font-size: 0.72rem; }
  .nv-raw-btn:hover { background: #3a3a4e; color: #e0e0e0; }
  .nv-triple-row { display: flex; gap: 0.5rem; padding: 0.2rem 0; font-size: 0.78rem; border-bottom: 1px solid #1e1e2e; }
  .nv-triple-row:last-child { border-bottom: none; }
  .nv-triple-pred { color: #8fc0df; min-width: 10rem; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .nv-triple-obj { color: #d0d0d0; word-break: break-all; }
  .nv-triple-empty { color: var(--clr-muted); font-size: 0.78rem; padding: 0.3rem 0; }
</style>
