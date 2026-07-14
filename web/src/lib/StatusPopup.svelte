<script>
  import { banner } from "./bannerStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";
  import AccountList from "@lightercore/ui/AccountList.svelte";
  import LlmProfileForm from "@lightercore/ui/LlmProfileForm.svelte";

  let { data = {} } = $props();
  let d = $derived(data || {});
  let showTech = $state(false);
  let activeProfileForm = $state(null); // "new" | "edit" | null
  let editingProfile = $state(null);

  // ── Prompt file editing (when data has _edit_name) ─────────────────────
  /** @type {string|null} */
  let editingName = $state(null);
  let editingContent = $state("");
  let editingDefault = $state("");
  let saving = $state(false);

  async function startEditing(name) {
    if (!name) return;
    try {
      const resp = await fetch(`/api/v1/llm/prompts/view?name=${encodeURIComponent(name)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      editingName = name;
      editingContent = data.current || data.default;
      editingDefault = data.default;
    } catch (err) {
      banner.show(`Failed to load prompt: ${err.message}`, "error", 5000);
      editingName = null;
    }
  }

  async function handleSave() {
    if (!editingName) return;
    saving = true;
    try {
      const resp = await fetch("/api/v1/llm/prompts/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editingName, content: editingContent }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      banner.show(`Prompt "${editingName}" saved`, "success");
      editingName = null;
      // Refresh the current tab data
      const viewResp = await fetch(`/api/v1/llm/prompts/view?name=${encodeURIComponent(editingName)}`);
      if (viewResp.ok) {
        const viewData = await viewResp.json();
        const activeTab = tabStore.active;
        if (activeTab && activeTab.id) {
          tabStore.update(activeTab.id, {
            ...viewData,
            details: viewData.current || viewData.default || "(empty)",
            _edit_name: editingName,
          });
        }
      }
    } catch (err) {
      banner.show(`Save failed: ${err.message}`, "error", 5000);
    } finally {
      saving = false;
    }
  }

  function cancelEdit() {
    editingName = null;
  }

  async function deleteProfile(item) {
    if (!confirm(`Delete profile "${item.name}"?`)) return;
    try {
      const resp = await fetch(`/api/v1/llm/profiles/${encodeURIComponent(item.name)}`, { method: "DELETE" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      banner.show(`Profile "${item.name}" deleted`, "success");
      refreshProfiles();
    } catch (err) {
      banner.show(`Activate failed: ${err.message}`, "error", 5000);
    }
  }

  async function activateProfile(item) {
    try {
      const resp = await fetch(`/api/v1/llm/profiles/${encodeURIComponent(item.name)}/load`, { method: "POST" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      banner.show(`Profile "${item.name}" activated`, "success");
      refreshProfiles();
    } catch (err) {
      banner.show(`Activate failed: ${err.message}`, "error", 5000);
    }
  }

  async function refreshProfiles() {
    try {
      const resp = await fetch("/api/v1/llm/profiles");
      if (!resp.ok) return;
      const data = await resp.json();
      const activeTab = tabStore.active;
      if (activeTab) {
        tabStore.update(activeTab.id, { ...d, profiles: data.profiles || [], _refreshed: Date.now() });
      }
    } catch (_) { /* silent */ }
  }

  function renderValue(val) {
    if (val === null || val === undefined) return "";
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  }

  /** Fields to treat as "technical detail" — hidden behind toggle. */
  const TECH_FIELDS = new Set([
    "created_at", "updated_at", "label_text", "definition_text",
    "_proof_count", "_proof_uuids", "_rank", "source",
  ]);

  function isTechField(key) {
    return TECH_FIELDS.has(key) || key.endsWith("_text");
  }

  function isMainField(key, val) {
    if (isTechField(key)) return false;
    // Raw JSON strings that are already rendered in summary
    if (key === "labels" && typeof val === "string" && val.startsWith("{")) return false;
    if (key === "definitions" && typeof val === "string" && val.startsWith("{")) return false;
    return true;
  }

  let techFieldCount = $derived(
    Object.entries(d).filter(([key, val]) => !isMainField(key, val)).length,
  );

  /** True when data represents a single entity (node or predicate) with triples. */
  function isDetailView() {
    if (!d.triples || !Array.isArray(d.triples)) return false;
    return d.node_id || d.predicate_id;
  }

  /** Parse a JSON string, returning the dict or null. */
  function tryParseJson(raw) {
    if (!raw || typeof raw !== "string") return null;
    try { return JSON.parse(raw); } catch { return null; }
  }

  /** Get first non-empty value from a JSON labels/definitions dict. */
  function firstValue(raw, locale) {
    const parsed = tryParseJson(raw);
    if (!parsed || typeof parsed !== "object") return null;
    // Try locale first, then first available
    if (locale && parsed[locale]) return parsed[locale];
    const values = Object.values(parsed);
    return values.length > 0 ? String(values[0]) : null;
  }

  let entityId = $derived(isDetailView() ? (d.node_id || d.predicate_id || "") : "");
  let entityType = $derived(isDetailView() ? (d.node_id ? "Node" : "Predicate") : "");
  let entityLabel = $derived(isDetailView() ? (firstValue(d.labels, "en") || "") : "");
  let entityDef = $derived(isDetailView() ? (firstValue(d.definitions, "en") || "") : "");

  /** Parse labels/definitions JSON into a {lang: text} dict or null. */
  function parseLangDict(raw) {
    const p = tryParseJson(raw);
    return (p && typeof p === "object" && !Array.isArray(p)) ? p : null;
  }

  let langLabels = $derived(isDetailView() ? parseLangDict(d.labels) : null);
  let langDefs = $derived(isDetailView() ? parseLangDict(d.definitions) : null);
  let langDescs = $derived(isDetailView() ? parseLangDict(d.descriptions) : null);
  let hasLangSections = $derived(
    (langLabels && Object.keys(langLabels).length > 0) ||
    (langDefs && Object.keys(langDefs).length > 0) ||
    (langDescs && Object.keys(langDescs).length > 0)
  );

  async function openNode(id) {
    if (!id) return;
    try {
      const resp = await fetch(`/api/v1/graph/nodes/${encodeURIComponent(id)}`);
      if (!resp.ok) return;
      const result = await resp.json();
      const node = result.node || result;
      tabStore.open("status", (node.labels ? firstValue(node.labels, "en") : null) || id, { ...node, triples: result.triples || [] }, {
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
      tabStore.open("status", (pred.labels ? firstValue(pred.labels, "en") : null) || id, { ...pred, triples: result.triples || [] }, {
        idKey: `pred-${id}`, replaceable: false,
      });
    } catch { /* silent */ }
  }

  /** Best label for a related entity in a triple row. */
  function tripleLabel(triple, role) {
    if (role === "subject") return triple._subject_label || triple.subject_id;
    if (role === "predicate") return triple._predicate_label || triple.predicate_id;
    if (role === "object") {
      if (triple.object_type === "uri") return triple._object_label || triple.object_value;
      return triple.object_value;
    }
    return "";
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
  {:else if Array.isArray(d.nodes)}
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
  {:else if Array.isArray(d.predicates)}
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
  {:else if isDetailView()}
    <div class="detail-header">
      <h3 class="detail-id">{entityId}</h3>
      {#if entityLabel}
        <div class="detail-label">{entityLabel}</div>
      {/if}
      {#if entityDef}
        <div class="detail-def">{entityDef}</div>
      {/if}
      <span class="detail-badge">{entityType}</span>
    </div>

    {#if hasLangSections}
      <div class="section-header">
        <h3 class="title">Labels / Definitions</h3>
      </div>
      <div class="lang-section">
        {#if langLabels}
          <div class="sub-label-inline">Labels</div>
          {#each Object.entries(langLabels) as [lang, text]}
            <div class="lang-row">
              <span class="lang-code">{lang}</span>
              <span class="lang-text">{text}</span>
            </div>
          {/each}
        {/if}
        {#if langDefs}
          <div class="lang-def-sep"></div>
          <div class="sub-label-inline">Definitions</div>
          {#each Object.entries(langDefs) as [lang, text]}
            <div class="lang-row def">
              <span class="lang-code">{lang}</span>
              <span class="lang-text">{text}</span>
            </div>
          {/each}
        {/if}
        {#if langDescs}
          <div class="lang-def-sep"></div>
          <div class="sub-label-inline">Descriptions</div>
          {#each Object.entries(langDescs) as [lang, text]}
            <div class="lang-row def">
              <span class="lang-code">{lang}</span>
              <span class="lang-text">{text}</span>
            </div>
          {/each}
        {/if}
      </div>
    {/if}

    <div class="section-header">
      <h3 class="title">Triples ({d.triples.length})</h3>
    </div>
    {#each d.triples as triple}
      <div class="triple-row">
        <span class="triple-label-arc">
          <span class="ent-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openNode(triple.subject_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.subject_id); } }}>
            {tripleLabel(triple, "subject")}
          </span>
          <span class="arrow">→</span>
          <span class="ent-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openPredicate(triple.predicate_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openPredicate(triple.predicate_id); } }}>
            {tripleLabel(triple, "predicate")}
          </span>
          <span class="arrow">→</span>
          {#if triple.object_type === "uri"}
            <span class="ent-link" role="button" tabindex="-1"
              onclick={(e) => { e.stopPropagation(); openNode(triple.object_value); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.object_value); } }}>
              {tripleLabel(triple, "object")}
            </span>
          {:else}
            <span class="obj-literal">{tripleLabel(triple, "object")}</span>
          {/if}
        </span>
        <span class="triple-id-arc">
          <span class="id-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openNode(triple.subject_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.subject_id); } }}>
            {triple.subject_id}
          </span>
          <span class="arrow">→</span>
          <span class="id-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openPredicate(triple.predicate_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openPredicate(triple.predicate_id); } }}>
            {triple.predicate_id}
          </span>
          <span class="arrow">→</span>
          {#if triple.object_type === "uri"}
            <span class="id-link" role="button" tabindex="-1"
              onclick={(e) => { e.stopPropagation(); openNode(triple.object_value); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.object_value); } }}>
              {triple.object_value}
            </span>
          {:else}
            <span class="obj-literal id">{triple.object_value}</span>
          {/if}
        </span>
      </div>
    {:else}
      <p class="empty">No triples.</p>
    {/each}
    {#if techFieldCount > 0}
      <button class="tech-toggle" onclick={() => { showTech = !showTech; }}>
        {showTech ? "Hide technical details" : "Show technical details"}
      </button>
      {#if showTech}
        {#each Object.entries(d) as [key, val]}
          {#if !isMainField(key, val) && key !== "triples"}
            <div class="row tech">
              <span class="key">{key}</span>
              <span class="val">{renderValue(val)}</span>
            </div>
          {/if}
        {/each}
      {/if}
    {/if}
  {:else if d.profiles !== undefined}
    <div class="profiles-section">
      <AccountList
        type="llm"
        items={d.profiles}
        activeName={d.active_profile || ""}
        onAdd={() => { activeProfileForm = "new"; }}
        onModify={(item) => { activeProfileForm = "edit"; editingProfile = item; }}
        onRemove={async (item) => { await deleteProfile(item); }}
        onActivate={async (item) => { await activateProfile(item); }}
      />
    </div>

    {#if activeProfileForm === "new" || activeProfileForm === "edit"}
      <LlmProfileForm
        profile={activeProfileForm === "edit" ? editingProfile : null}
        onSaved={() => { activeProfileForm = null; editingProfile = null; refreshProfiles(); }}
        onDismiss={() => { activeProfileForm = null; editingProfile = null; }}
      />
    {/if}

  {:else if Array.isArray(d.triples)}
    <div class="section-header">
      <h3 class="title">Triples ({d.triples.length})</h3>
    </div>
    {#each d.triples as triple}
      <div class="triple-row">
        <span class="triple-label-arc">
          <span class="ent-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openNode(triple.subject_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.subject_id); } }}>
            {tripleLabel(triple, "subject")}
          </span>
          <span class="arrow">→</span>
          <span class="ent-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openPredicate(triple.predicate_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openPredicate(triple.predicate_id); } }}>
            {tripleLabel(triple, "predicate")}
          </span>
          <span class="arrow">→</span>
          {#if triple.object_type === "uri"}
            <span class="ent-link" role="button" tabindex="-1"
              onclick={(e) => { e.stopPropagation(); openNode(triple.object_value); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.object_value); } }}>
              {tripleLabel(triple, "object")}
            </span>
          {:else}
            <span class="obj-literal">{tripleLabel(triple, "object")}</span>
          {/if}
        </span>
        <span class="triple-id-arc">
          <span class="id-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openNode(triple.subject_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.subject_id); } }}>
            {triple.subject_id}
          </span>
          <span class="arrow">→</span>
          <span class="id-link" role="button" tabindex="-1"
            onclick={(e) => { e.stopPropagation(); openPredicate(triple.predicate_id); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openPredicate(triple.predicate_id); } }}>
            {triple.predicate_id}
          </span>
          <span class="arrow">→</span>
          {#if triple.object_type === "uri"}
            <span class="id-link" role="button" tabindex="-1"
              onclick={(e) => { e.stopPropagation(); openNode(triple.object_value); }}
            onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); openNode(triple.object_value); } }}>
              {triple.object_value}
            </span>
          {:else}
            <span class="obj-literal id">{triple.object_value}</span>
          {/if}
        </span>
      </div>
    {:else}
      <p class="empty">No triples.</p>
    {/each}
  {:else if d.reply}
    <div class="message">{d.reply}</div>
  {:else if d.details !== undefined}
    <div class="prompt-view">
      <div class="prompt-view-header">
        {#if d.message}
          <p class="prompt-view-meta">{@html d.message}</p>
        {/if}
        {#if d._edit_name}
          <button class="btn btn-edit" onclick={() => startEditing(d._edit_name)} title="Edit this prompt file">
            Edit
          </button>
        {/if}
      </div>
      <pre class="prompt-content">{d.details}</pre>
    </div>
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
      {#if isMainField(key, val)}
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
      {/if}
    {/each}
    {#if Object.keys(d).length === 0}
      <p class="message">No data.</p>
    {:else if techFieldCount > 0}
      <button class="tech-toggle" onclick={() => { showTech = !showTech; }}>
        {showTech ? "Hide technical details" : "Show technical details"}
      </button>
      {#if showTech}
        {#each Object.entries(d) as [key, val]}
          {#if !isMainField(key, val)}
            <div class="row tech">
              <span class="key">{key}</span>
              <span class="val">{renderValue(val)}</span>
            </div>
          {/if}
        {/each}
      {/if}
    {/if}
  {/if}

  {#if editingName !== null}
    <!-- Edit dialog overlay -->
    <div class="edit-overlay" onclick={cancelEdit} role="dialog" aria-modal="true" aria-label="Edit prompt"
         tabindex="0" onkeydown={(e) => { if (e.key === "Escape") cancelEdit(); }}>
      <div class="edit-dialog" role="presentation" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
        <div class="edit-header">
          <h3>Edit: {editingName}</h3>
          <button class="btn-close" onclick={cancelEdit}>✕</button>
        </div>
        <textarea
          class="edit-textarea"
          bind:value={editingContent}
          rows="20"
          spellcheck="false"
        ></textarea>
        <div class="edit-actions">
          <button class="btn btn-save" onclick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button class="btn btn-cancel" onclick={cancelEdit}>Cancel</button>
          <button class="btn btn-reset" onclick={() => { editingContent = editingDefault; }} title="Restore default">
            Restore Default
          </button>
        </div>
      </div>
    </div>
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
  .detail-header {
    padding: 0.75rem;
    border-bottom: 1px solid #2a2a3e;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .detail-id {
    font-size: 1rem;
    color: #e0e0e0;
    font-weight: 700;
  }
  .detail-label {
    font-size: 0.9rem;
    color: #c0c0d0;
    font-style: italic;
  }
  .detail-def {
    font-size: 0.8rem;
    color: var(--clr-sub);
  }
  .detail-badge {
    display: inline-block;
    align-self: flex-start;
    font-size: 0.65rem;
    padding: 1px 6px;
    border-radius: 3px;
    background: #2a2a4a;
    color: var(--clr-sub);
    text-transform: uppercase;
    letter-spacing: 0.5px;
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
  .tech-toggle {
    display: block;
    width: 100%;
    padding: 0.4rem;
    background: #22223a;
    border: 1px solid #333;
    border-radius: 4px;
    color: var(--clr-sub);
    font-family: monospace;
    font-size: 0.75rem;
    cursor: pointer;
    margin-top: 0.5rem;
  }
  .tech-toggle:hover {
    background: #2a2a4a;
    color: #e0e0e0;
  }
  .row.tech {
    opacity: 0.65;
    font-size: 0.78rem;
  }

  /* ── Language labels/definitions section ────────────── */
  .lang-section { padding: 0.25rem 0.75rem 0.5rem; border-bottom: 1px solid #2a2a3e; }
  .lang-row { display: flex; gap: 0.5rem; padding: 0.15rem 0; align-items: baseline; }
  .lang-code { color: var(--clr-sub); font-size: 0.75rem; min-width: 2.5rem; text-transform: uppercase; }
  .lang-text { color: #e0e0e0; font-size: 0.85rem; }
  .lang-row.def .lang-text { color: var(--clr-sub); font-style: italic; }
  .lang-def-sep { height: 0.3rem; }
  .sub-label-inline { font-size: 0.72rem; color: var(--clr-sub); text-transform: uppercase; letter-spacing: 0.5px; margin: 0.15rem 0; }

  /* ── Triple row with dual-arc ───────────────────────── */
  .triple-row {
    display: flex; align-items: center; gap: 0.3rem;
    padding: 0.3rem 0.75rem; border-bottom: 1px solid #2a2a3e;
  }
  .triple-row:last-child { border-bottom: none; }
  .triple-label-arc { flex: 1; min-width: 0; display: flex; align-items: center; gap: 0.25rem; overflow: hidden; }
  .triple-id-arc { display: flex; align-items: center; gap: 0.2rem; flex-shrink: 0; max-width: 45%; color: var(--clr-dim); font-size: 0.78rem; overflow: hidden; }
  .ent-link { cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 2px; border-radius: 2px; transition: background 0.1s; color: #7cf; font-weight: 500; }
  .ent-link:hover { background: rgba(255,255,255,0.08); text-decoration: underline; }
  .id-link { cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 2px; border-radius: 2px; color: #5ab; }
  .id-link:hover { background: rgba(255,255,255,0.08); text-decoration: underline; }
  .obj-literal { color: #e0e0e0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .obj-literal.id { color: #aaa; font-size: 0.78rem; }

  /* ── Prompt file view ────────────────────────────────── */
  .prompt-view { padding: 0.75rem; display: flex; flex-direction: column; gap: 0.5rem; height: 100%; }
  .prompt-view-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
  .prompt-view-meta { color: var(--clr-sub); font-size: 0.85rem; margin: 0; flex: 1; }
  .prompt-content {
    flex: 1; overflow: auto; background: #111; color: #a0d0a0;
    border: 1px solid #333; border-radius: 4px;
    padding: 0.75rem; font-family: monospace; font-size: 0.78rem;
    line-height: 1.5; white-space: pre-wrap; margin: 0;
  }
  .btn {
    padding: 0.25rem 0.6rem; border: 1px solid #444; border-radius: 4px;
    background: #2a2a3e; color: #e0e0e0; cursor: pointer;
    font-size: 0.75rem; white-space: nowrap;
  }
  .btn:hover { background: #3a3a5a; }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .btn-edit { background: #2a3a4a; border-color: #3a6a8a; }
  .btn-save { background: #2a4a3a; border-color: #3a7a4a; }
  .btn-cancel { background: #3a3a3a; border-color: #555; }
  .btn-reset { background: #3a2a2a; border-color: #7a3a3a; }
  .btn-close { background: none; border: none; color: #888; cursor: pointer; font-size: 1rem; }
  .btn-close:hover { color: #e0e0e0; }

  /* ── Edit dialog overlay ─────────────────────────────── */
  .edit-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center; z-index: 100;
  }
  .edit-dialog {
    background: #1e1e32; border: 1px solid #444; border-radius: 8px;
    padding: 1rem; width: 90%; max-width: 700px;
    max-height: 85vh; display: flex; flex-direction: column;
  }
  .edit-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 0.5rem;
  }
  .edit-header h3 { margin: 0; font-size: 0.95rem; color: #e0e0e0; }
  .edit-textarea {
    flex: 1; min-height: 300px;
    background: #111; color: #a0d0a0; border: 1px solid #333; border-radius: 4px;
    padding: 0.75rem; font-family: monospace; font-size: 0.8rem;
    resize: vertical; outline: none; line-height: 1.5;
  }
  .edit-textarea:focus { border-color: #5a5a8a; }
  .edit-actions {
    display: flex; gap: 0.5rem; justify-content: flex-end;
    margin-top: 0.75rem;
  }
</style>
