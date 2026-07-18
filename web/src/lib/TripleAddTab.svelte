<script>
  /**
   * TripleAddTab — multi-row triple entry with toolbar, autocomplete,
   * abbreviation, object-type selector, pre-submit validation, and
   * per-row error display.
   */

  import { createHistory } from "./historyStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";
  import {
    TYPE_FLAG_MAP,
    interpretFlag,
    parseFlagFromValue,
    resolveObjectType,
    OBJECT_TYPE_LABELS,
    OBJECT_TYPE_ITEMS as OBJECT_TYPES,
    getBoolSuggestions,
    getFlagSuggestions,
  } from "./tripleAddTypeUtils.js";

  /** Row data model */
  function makeRow(overrides = {}) {
    return {
      subject_id: overrides.subject_id ?? "",
      predicate_id: overrides.predicate_id ?? "",
      object_value: overrides.object_value ?? "",
      object_type: overrides.object_type ?? "node",
      object_datatype: overrides.object_datatype ?? null,
      object_lang: overrides.object_lang ?? null,
      _key: "row-" + Math.random().toString(36).slice(2, 8),
      _error: null,     // { field: "subject_id" | "predicate_id" | "object_value", message: string }
      _status: "editing", // "editing" | "created" | "duplicate" | "error" | "skipped"
    };
  }

  let { data = {} } = $props();

  // ── State ──────────────────────────────────────────────────────────
  let rows = $state([makeRow()]);
  let hist = createHistory(rows);
  let selectionMode = $state(false);
  let selected = $state(new Set());
  let submitting = $state(false);
  let submitResult = $state(null); // batch result JSON or null
  let showDiscardConfirm = $state(false);
  let showSubmitConfirm = $state(false);
  let insertRowNumber = $state("");
  let showInsertDialog = $state(false);

  // Autocomplete state
  let autocompleteCache = {
    nodes: {},   // query -> [{node_id, label}]
    predicates: {}, // query -> [{predicate_id, label}]
  };
  let autocompleteTimeouts = {};

  // ── Derived ────────────────────────────────────────────────────────
  let dirty = $derived(rows.some(r => r._status === "editing"));
  let hasErrors = $derived(rows.some(r => r._error !== null));
  let selectedRows = $derived(rows.filter(r => selected.has(r._key)));
  let canSubmit = $derived(
    !submitting && dirty && !hasErrors && rows.some(r => r.subject_id || r.predicate_id || r.object_value)
  );

  // ── Row management ─────────────────────────────────────────────────
  // OBJECT_TYPES, TYPE_FLAG_MAP, interpretFlag, parseFlagFromValue,
  // and resolveObjectType are imported from tripleAddTypeUtils.js

  /** Update the OBJECT field's <datalist> content based on input prefix. */
  function updateObjectDatalist(value, rowKey, currentType) {
    const datalist = document.getElementById(`dl-${rowKey}-obj`);
    if (!datalist) return;
    if (value.startsWith("--")) {
      // Show CLI flag suggestions — dynamically generated from TYPE_FLAG_MAP
      datalist.innerHTML = getFlagSuggestions()
        .map(f => `<option value="${f}">`).join("");
    } else if (currentType === "bool") {
      // Show TRUE / FALSE suggestions for boolean literals
      datalist.innerHTML = getBoolSuggestions()
        .map(s => `<option value="${s.id}">${s.label}</option>`).join("");
    } else if (currentType === "node" && value.length >= 2) {
      // Debounced node autocomplete
      clearTimeout(autocompleteTimeouts[rowKey + "-obj"]);
      autocompleteTimeouts[rowKey + "-obj"] = setTimeout(async () => {
        const suggestions = await fetchSuggestions(value, "nodes");
        if (datalist) {
          datalist.innerHTML = suggestions.map(s =>
            `<option value="${s.id}">${s.label}</option>`
          ).join("");
        }
      }, 300);
    } else {
      datalist.innerHTML = "";
    }
  }

  /** Unified handler for object_value <input> — parses --flag and syncs type. */
  function handleObjectInput(e, row) {
    const raw = e.target.value;
    const { flag, rest } = parseFlagFromValue(raw);
    if (flag) {
      const typeInfo = interpretFlag(flag);
      if (typeInfo) {
        row.object_type = typeInfo.object_type;
        row.object_datatype = typeInfo.object_datatype;
        row.object_lang = null;
        // Defer value clearing to a microtask so the browser can process
        // the native <datalist> popup (which appears during the input event)
        // before we programmatically clear the value.  This prevents Svelte's
        // reactive DOM update from dismissing the popup prematurely.
        queueMicrotask(() => {
          row.object_value = rest;
        });
        clearRowError(row);
      } else {
        // Unknown flag: show inline warning, keep raw text as-is
        row.object_value = raw;
        row._error = { field: "object_type", message: `Unknown type: --${flag}` };
      }
    } else {
      row.object_value = raw;
      clearRowError(row);
      // No flag detected; if raw starts with "--" but no space yet,
      // the user is still typing the flag word — don't change type (efficiency hack)
    }
    updateObjectDatalist(raw, row._key, resolveObjectType(row));
  }

  function setObjectType(row, typeId) {
    row.object_type = "node";
    row.object_datatype = null;
    row.object_lang = null;
    switch (typeId) {
      case "node":  row.object_type = "node"; break;
      case "literal": row.object_type = "literal"; break;
      case "int":   row.object_type = "literal"; row.object_datatype = "xsd:integer"; break;
      case "float": row.object_type = "literal"; row.object_datatype = "xsd:decimal"; break;
      case "bool":  row.object_type = "literal"; row.object_datatype = "xsd:boolean"; break;
      case "url":   row.object_type = "literal"; row.object_datatype = "xsd:anyURI"; break;
      case "katex": row.object_type = "literal"; row.object_datatype = "text/katex"; break;
    }
    // If the value still has a stale --flag prefix from the previous type, strip it
    const { flag, rest } = parseFlagFromValue(row.object_value);
    if (flag) {
      queueMicrotask(() => {
        row.object_value = rest;
      });
    }
    clearRowError(row);
    updateObjectDatalist(row.object_value, row._key, resolveObjectType(row));
  }

  function addRow() {
    clearAllErrors();
    const newRows = [...rows, makeRow()];
    hist.push(newRows);
    rows = newRows;
    // Focus the new row's subject field
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-row-key="${rows[rows.length - 1]._key}"][data-field="subject_id"]`);
      el?.focus();
    });
  }

  function insertRow() {
    const idx = parseInt(insertRowNumber, 10);
    if (isNaN(idx) || idx < 0 || idx > rows.length) return;
    clearAllErrors();
    const newRows = [...rows];
    newRows.splice(idx, 0, makeRow());
    hist.push(newRows);
    rows = newRows;
    showInsertDialog = false;
    insertRowNumber = "";
  }

  function deleteRow(key) {
    clearAllErrors();
    const idx = rows.findIndex(r => r._key === key);
    if (idx === -1) return;
    const newRows = rows.filter(r => r._key !== key);
    hist.push(newRows);
    rows = newRows;
    selected.delete(key);
  }

  function deleteSelectedRows() {
    const keys = Array.from(selected);
    clearAllErrors();
    const newRows = rows.filter(r => !selected.has(r._key));
    hist.push(newRows);
    rows = newRows;
    selected = new Set();
  }

  // ── Abbreviation ──────────────────────────────────────────────────
  function abbreviateRows(rowList) {
    let lastSubject = "", lastPredicate = "", lastObject = "", lastType = "node", lastDt = null;
    return rowList.map(r => {
      const subject = r.subject_id || lastSubject;
      const pred = r.predicate_id || lastPredicate;
      const obj = r.object_value || lastObject;
      const type = r.object_value ? r.object_type : lastType;
      const dt = r.object_value ? r.object_datatype : lastDt;
      if (r.subject_id) lastSubject = r.subject_id;
      if (r.predicate_id) lastPredicate = r.predicate_id;
      if (r.object_value) { lastObject = r.object_value; lastType = r.object_type; lastDt = r.object_datatype; }
      return { ...r, subject_id: subject, predicate_id: pred, object_value: obj, object_type: type, object_datatype: dt };
    });
  }

  // ── Pre-submit validation ──────────────────────────────────────────
  function validateRows(rowList) {
    let valid = true;
    for (const r of rowList) {
      r._error = null;
      if (!r.subject_id && !r.predicate_id && !r.object_value) continue; // skip empty
      if (!r.subject_id) { r._error = { field: "subject_id", message: "Subject is required" }; valid = false; continue; }
      if (!r.predicate_id) { r._error = { field: "predicate_id", message: "Predicate is required" }; valid = false; continue; }
      if (!r.object_value) { r._error = { field: "object_value", message: "Object is required" }; valid = false; continue; }
      // Validate literal values
      const ot = resolveObjectType(r);
      if (ot === "int" && isNaN(parseInt(r.object_value, 10))) {
        r._error = { field: "object_value", message: "Must be an integer" }; valid = false;
      }
      if (ot === "float" && isNaN(parseFloat(r.object_value))) {
        r._error = { field: "object_value", message: "Must be a number" }; valid = false;
      }
      if (ot === "url") {
        try { new URL(r.object_value); } catch {
          r._error = { field: "object_value", message: "Must be a valid URL (http://, https://, etc.)" }; valid = false;
        }
      }
      // Check for duplicates within batch
      for (const other of rowList) {
        if (other === r || other._status !== "editing") continue;
        if (other.subject_id === r.subject_id && other.predicate_id === r.predicate_id && other.object_value === r.object_value) {
          r._error = { field: "object_value", message: "Duplicate triple in batch" }; valid = false;
          break;
        }
      }
    }
    return valid;
  }

  function clearAllErrors() {
    for (const r of rows) r._error = null;
  }

  function clearRowError(row) {
    row._error = null;
  }

  // ── Submission ─────────────────────────────────────────────────────
  async function handleDiscard() {
    showDiscardConfirm = false;
    tabStore.close(tabStore.active?.id);
  }

  async function handleSubmit() {
    showSubmitConfirm = false;
    // 1. Abbreviate
    const abbreviated = abbreviateRows(rows);
    // 2. Validate all rows before submission
    if (!validateRows(abbreviated)) {
      rows = abbreviated; // show errors
      return;
    }
    // 3. Build payload (strip --flag prefix from object_value as safety net)
    const payload = abbreviated
      .filter(r => r.subject_id && r.predicate_id && r.object_value)
      .map(r => {
        let object_value = r.object_value;
        let object_type = r.object_type;
        let object_datatype = r.object_datatype;
        let object_lang = r.object_lang;
        const { flag, rest } = parseFlagFromValue(object_value);
        if (flag) {
          const typeInfo = interpretFlag(flag);
          if (typeInfo) {
            object_type = typeInfo.object_type;
            object_datatype = typeInfo.object_datatype;
            object_lang = null;
          }
          object_value = rest;
        }
        return {
          subject_id: r.subject_id,
          predicate_id: r.predicate_id,
          object_value,
          object_type,
          object_datatype,
          object_lang,
        };
      });
    if (payload.length === 0) return;
    // 4. Submit
    submitting = true;
    try {
      const resp = await fetch("/api/v1/graph/triples/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ triples: payload }),
      });
      const result = await resp.json();
      submitResult = result;
      // Apply status to rows
      const activeRows = rows.filter(r => r.subject_id && r.predicate_id && r.object_value);
      for (const res of result.results) {
        const rowIdx = res.row;
        const payloadEntry = payload[rowIdx];
        // Match by row index and content (the batch endpoint returns 1:1 order)
        if (rowIdx < activeRows.length) {
          activeRows[rowIdx]._status = res.status === "created" ? "created"
            : res.status === "duplicate" ? "duplicate"
            : res.status === "error" ? "error"
            : "skipped";
          if (res.status === "error") {
            activeRows[rowIdx]._error = { field: "object_value", message: res.message || "Creation failed" };
          }
        }
      }
    } catch (err) {
      for (const r of rows) {
        if (r._status === "editing") r._error = { field: "object_value", message: `Network error: ${err.message}` };
      }
    } finally {
      submitting = false;
    }
  }

  async function retryFailed() {
    const failed = rows.filter(r => r._status === "error" || r._status === "duplicate");
    for (const r of failed) {
      r._error = null;
      r._status = "editing";
    }
    submitResult = null;
  }

  function viewTriples() {
    tabStore.close(tabStore.active?.id);
    tabStore.open("form", "Add Triple", {
      form: "triple-add", commandPath: ["triple", "add"],
      initialData: { _returnType: "triple-list", _returnTitle: "Triples" },
    }, { idKey: "triple-add" });
  }

  // ── Autocomplete ───────────────────────────────────────────────────
  async function fetchSuggestions(query, type) {
    if (query.length < 2) return [];
    if (autocompleteCache[type]?.[query]) return autocompleteCache[type][query];
    const endpoint = type === "nodes"
      ? `/api/v1/graph/nodes/search?q=${encodeURIComponent(query)}&limit=10`
      : `/api/v1/graph/predicates/search?q=${encodeURIComponent(query)}&limit=10`;
    try {
      const resp = await fetch(endpoint);
      if (!resp.ok) return [];
      const data = await resp.json();
      const items = data.results || data.data || [];
      const keyField = type === "nodes" ? "node_id" : "predicate_id";
      const suggestions = items.map(item => ({
        id: item[keyField],
        label: item.labels ? (Object.values(item.labels).find(v => v) || item[keyField]) : item[keyField],
      }));
      autocompleteCache[type] = { ...autocompleteCache[type], [query]: suggestions };
      return suggestions;
    } catch {
      return [];
    }
  }

  function debouncedAutocomplete(e, type) {
    const query = e.target.value;
    const key = e.target.dataset.rowKey;
    if (!query || query.length < 2) return;
    clearTimeout(autocompleteTimeouts[key + type]);
    autocompleteTimeouts[key + type] = setTimeout(async () => {
      const suggestions = await fetchSuggestions(query, type);
      // Store suggestions next to the input via a datalist
      const datalist = document.getElementById(`dl-${key}-${type}`);
      if (datalist) {
        datalist.innerHTML = suggestions.map(s =>
          `<option value="${s.id}">${s.label}</option>`
        ).join("");
      }
    }, 300);
  }

  // ── Keyboard shortcuts ─────────────────────────────────────────────
  function handleKeydown(e) {
    const tag = e.target.tagName;
    const ctrl = e.ctrlKey || e.metaKey;

    // Allow clipboard shortcuts in inputs
    if ((tag === "INPUT" || tag === "TEXTAREA") && ctrl && ["z", "Z", "y", "Y"].includes(e.key)) {
      // Handle Ctrl+Z/Y for undo/redo
      if (ctrl && e.key === "z" && !e.shiftKey) { e.preventDefault(); hist.undo(); return; }
      if (ctrl && (e.key === "y" || (e.key === "Z" && e.shiftKey))) { e.preventDefault(); hist.redo(); return; }
      return; // Let other shortcuts pass through input
    }

    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) {
      // Let normal text input handle its own shortcuts
      if (!ctrl) return;
    }

    if (showDiscardConfirm || showSubmitConfirm) return;

    // Undo/Redo (always available)
    if (ctrl && e.key === "z" && !e.shiftKey) { e.preventDefault(); hist.undo(); return; }
    if (ctrl && (e.key === "y" || (e.key === "Z" && e.shiftKey))) { e.preventDefault(); hist.redo(); return; }

    // New row
    if (ctrl && e.key === "n") { e.preventDefault(); addRow(); return; }

    // Insert row
    if (ctrl && e.shiftKey && e.key === "N") {
      e.preventDefault();
      showInsertDialog = true;
      insertRowNumber = String(rows.length);
      return;
    }

    // Submit
    if (ctrl && e.key === "Enter") {
      e.preventDefault();
      if (canSubmit) showSubmitConfirm = true;
      return;
    }

    // Discard
    if (ctrl && e.shiftKey && (e.key === "Delete" || e.key === "Backspace")) {
      e.preventDefault();
      if (dirty) showDiscardConfirm = true;
      return;
    }

    // Toggle selection
    if (e.key === "v" && !ctrl && !e.altKey) {
      if (tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        toggleSelectionMode();
      }
    }

    // Delete selected in selection mode
    if (e.key === "Delete" || e.key === "Backspace") {
      if (selectionMode && selected.size > 0 && tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        deleteSelectedRows();
      }
    }
  }

  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) selected = new Set();
  }

  function toggleRow(key) {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key); else next.add(key);
    selected = next;
  }

  // ── Object type label helper (for the badge-like display) ──────────
  function objectTypeLabel(row) {
    return OBJECT_TYPE_LABELS[resolveObjectType(row)] || resolveObjectType(row);
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="triple-add-tab">
  {#if submitResult}
    <!-- ── Post-submit result view ── -->
    <div class="result-view">
      <div class="result-summary">
        <span class="result-badge success">{submitResult.created_count} created</span>
        {#if submitResult.duplicate_count > 0}
          <span class="result-badge warning">{submitResult.duplicate_count} duplicates</span>
        {/if}
        {#if submitResult.error_count > 0}
          <span class="result-badge error">{submitResult.error_count} errors</span>
        {/if}
      </div>
      <div class="result-actions">
        {#if submitResult.error_count > 0}
          <button class="btn-small" onclick={retryFailed}>Retry failed</button>
        {/if}
        <button class="btn-small" onclick={viewTriples}>View triples</button>
      </div>
    </div>
  {:else}
    <!-- ── Toolbar ── -->
    <div class="toolbar">
      {#if selectionMode}
        <span class="sel-info">{selected.size} selected</span>
        <button class="btn-small" onclick={toggleSelectionMode}>Cancel</button>
        <button class="btn-small danger" onclick={deleteSelectedRows}
          disabled={selected.size === 0}>Delete</button>
      {:else}
        <button class="btn-small" onclick={addRow} title="Ctrl+N">+ New</button>
        <button class="btn-small" onclick={() => { showInsertDialog = true; insertRowNumber = String(rows.length); }}
          title="Ctrl+Shift+N">Insert</button>
        <button class="btn-small" onclick={() => hist.undo()} disabled={!hist.canUndo}
          title="Ctrl+Z">Undo</button>
        <button class="btn-small" onclick={() => hist.redo()} disabled={!hist.canRedo}
          title="Ctrl+Y">Redo</button>
        <button class="btn-small" onclick={toggleSelectionMode}>v Select</button>
      {/if}
    </div>

    <!-- ── Insert row dialog ── -->
    {#if showInsertDialog}
      <div class="insert-dialog-overlay" role="presentation" onclick={() => { showInsertDialog = false; }}>
        <div class="insert-dialog" role="dialog" onclick={(e) => e.stopPropagation()}>
          <span>Insert at row</span>
          <input type="number" min="0" max={rows.length} bind:value={insertRowNumber}
            onkeydown={(e) => { if (e.key === "Enter") insertRow(); if (e.key === "Escape") showInsertDialog = false; }} />
          <button class="btn-small" onclick={insertRow}>Insert</button>
        </div>
      </div>
    {/if}

    <!-- ── Column headers ── -->
    <div class="row-header">
      {#if selectionMode}<span class="col-check"></span>{/if}
      <span class="col-subj">SUBJECT</span>
      <span class="col-pred">PREDICATE</span>
      <span class="col-obj">OBJECT</span>
      <span class="col-type">Type</span>
      <span class="col-del"></span>
    </div>

    <!-- ── Rows ── -->
    <div class="rows-scroll">
      {#each rows as row, i (row._key)}
        <div class="row" class:row-error={row._error} class:row-created={row._status === "created"}
          class:row-duplicate={row._status === "duplicate"} class:row-skipped={row._status === "skipped"}>
          {#if selectionMode}
            <span class="col-check">
              <input type="checkbox" checked={selected.has(row._key)}
                onchange={() => toggleRow(row._key)} />
            </span>
          {/if}

          <!-- SUBJECT -->
          <span class="col-subj">
            <input data-row-key={row._key} data-field="subject_id"
              type="text" placeholder="Node ID (e.g. ALICE)"
              value={row.subject_id}
              oninput={(e) => { row.subject_id = e.target.value; clearRowError(row); debouncedAutocomplete(e, "nodes"); }}
              disabled={row._status !== "editing"}
              list={"dl-" + row._key + "-nodes"} />
            <datalist id={"dl-" + row._key + "-nodes"}></datalist>
            {#if row._error?.field === "subject_id"}
              <span class="field-error">{row._error.message}</span>
            {/if}
          </span>

          <!-- PREDICATE -->
          <span class="col-pred">
            <input data-row-key={row._key} data-field="predicate_id"
              type="text" placeholder="Predicate ID (e.g. ex:knows)"
              value={row.predicate_id}
              oninput={(e) => { row.predicate_id = e.target.value; clearRowError(row); debouncedAutocomplete(e, "preds"); }}
              disabled={row._status !== "editing"}
              list={"dl-" + row._key + "-preds"} />
            <datalist id={"dl-" + row._key + "-preds"}></datalist>
            {#if row._error?.field === "predicate_id"}
              <span class="field-error">{row._error.message}</span>
            {/if}
          </span>

          <!-- OBJECT -->
          <span class="col-obj">
            <input data-row-key={row._key} data-field="object_value"
              type="text"
              inputmode={resolveObjectType(row) === "int" || resolveObjectType(row) === "float" ? "decimal" : resolveObjectType(row) === "url" ? "url" : undefined}
              placeholder={resolveObjectType(row) === "node" ? "Node ID (e.g. BOB)" : resolveObjectType(row) === "url" ? "https://..." : resolveObjectType(row) === "katex" ? "E = mc^2" : resolveObjectType(row) === "int" ? "Integer" : resolveObjectType(row) === "float" ? "Decimal" : resolveObjectType(row) === "bool" ? "true / false" : "Literal value or --flag value"}
              value={row.object_value}
              oninput={(e) => { handleObjectInput(e, row); }}
              disabled={row._status !== "editing"}
              list={"dl-" + row._key + "-obj"} />
            <datalist id={"dl-" + row._key + "-obj"}></datalist>
            {#if row._error?.field === "object_value"}
              <span class="field-error">{row._error.message}</span>
            {/if}
          </span>

          <!-- Type selector (dropdown) -->
          <span class="col-type">
            {#if row._status === "editing"}
              <select class="type-select" value={resolveObjectType(row)}
                onchange={(e) => setObjectType(row, e.target.value)}
                disabled={row._status !== "editing"}>
                {#each OBJECT_TYPES as ot}
                  <option value={ot.id}>{ot.icon} {ot.label}</option>
                {/each}
              </select>
              {#if row._error?.field === "object_type"}
                <span class="field-error type-warning">{row._error.message}</span>
              {/if}
            {:else}
              <span class="type-badge type-{resolveObjectType(row)}">{objectTypeLabel(row)}</span>
            {/if}
          </span>

          <!-- Delete -->
          <span class="col-del">
            {#if row._status === "editing"}
              <button class="btn-icon del-btn" onclick={() => deleteRow(row._key)}
                title="Delete row">x</button>
            {:else if row._status === "created"}
              <span class="status-icon created" title="Created">&#x2713;</span>
            {:else if row._status === "duplicate"}
              <span class="status-icon duplicate" title="Already exists">!</span>
            {:else if row._status === "error"}
              <span class="status-icon error" title="Error">&#x2717;</span>
            {/if}
          </span>
        </div>
      {/each}
    </div>

    <!-- ── Actions ── -->
    <div class="actions">
      <button class="btn-small danger" onclick={() => { if (dirty) showDiscardConfirm = true; else handleDiscard(); }}
        disabled={submitting}
        title="Ctrl+Shift+Delete">
        Discard
      </button>
      <button class="btn-small submit-btn" onclick={() => { if (canSubmit) showSubmitConfirm = true; }}
        disabled={!canSubmit}
        title="Ctrl+Enter">
        {submitting ? "Submitting\u2026" : "Submit"}
      </button>
    </div>
  {/if}
</div>

<!-- ── Confirm dialogs ── -->
{#if showDiscardConfirm}
  <div class="confirm-overlay" role="presentation" onclick={() => { showDiscardConfirm = false; }}>
    <div class="confirm-dialog" role="alertdialog" onclick={(e) => e.stopPropagation()}>
      <p>Discard all unsaved triples? This action is irreversible.</p>
      <div class="confirm-actions">
        <button class="btn-small" onclick={() => { showDiscardConfirm = false; }}>Cancel</button>
        <button class="btn-small danger" onclick={handleDiscard}>Discard</button>
      </div>
    </div>
  </div>
{/if}

{#if showSubmitConfirm}
  <div class="confirm-overlay" role="presentation" onclick={() => { showSubmitConfirm = false; }}>
    <div class="confirm-dialog" role="alertdialog" onclick={(e) => e.stopPropagation()}>
      <p>Submit {rows.filter(r => r.subject_id || r.predicate_id || r.object_value).length} triple(s)?</p>
      <div class="confirm-actions">
        <button class="btn-small" onclick={() => { showSubmitConfirm = false; }}>Cancel</button>
        <button class="btn-small submit-btn" onclick={handleSubmit}>Submit</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .triple-add-tab { display: flex; flex-direction: column; height: 100%; font-family: monospace; font-size: 0.82rem; position: relative; }

  /* Toolbar */
  .toolbar { display: flex; align-items: center; gap: 6px; padding: 0.4rem 0.75rem; border-bottom: 1px solid #2a2a3e; background: #1a1a2e; flex-shrink: 0; }
  .sel-info { color: var(--clr-sub); font-size: 0.8rem; }
  .btn-small { padding: 0.2rem 0.5rem; background: #2a2a3e; border: 1px solid #444; border-radius: 3px; color: #e0e0e0; cursor: pointer; font-family: monospace; font-size: 0.78rem; }
  .btn-small:hover { background: #3a3a4e; }
  .btn-small:disabled { opacity: 0.4; cursor: default; }
  .btn-small.danger { border-color: #a33; color: #f77; }
  .btn-small.danger:hover { background: #3a1a1a; }
  .submit-btn { background: #3a6a3a; color: #e0e0e0; border-color: #4a8a4a; }
  .submit-btn:hover { background: #4a8a4a; }

  /* Column headers */
  .row-header { display: flex; align-items: center; gap: 4px; padding: 0.3rem 0.75rem; border-bottom: 1px solid #2a2a3e; font-size: 0.7rem; color: #7c7c9a; font-weight: 700; text-transform: uppercase; flex-shrink: 0; }
  .col-check { width: 28px; flex-shrink: 0; }
  .col-subj { flex: 1; min-width: 120px; }
  .col-pred { flex: 1; min-width: 120px; }
  .col-obj { flex: 1; min-width: 120px; }
  .col-type { width: 120px; flex-shrink: 0; }
  .col-del { width: 28px; flex-shrink: 0; text-align: center; }

  /* Rows */
  .rows-scroll { flex: 1; overflow-y: auto; }
  .row { display: flex; align-items: flex-start; gap: 4px; padding: 0.4rem 0.75rem; border-bottom: 1px solid #222; }
  .row:hover { background: #1e1e34; }
  .row.row-error { background: #2a1a1a; }
  .row.row-created { background: #1a2a1a; }
  .row.row-duplicate { background: #2a2a1a; }
  .row.row-skipped { opacity: 0.5; }

  .row input, .row select {
    width: 100%; padding: 0.3rem 0.5rem; background: #2a2a3e; border: 1px solid #444;
    border-radius: 3px; color: #e0e0e0; font-family: monospace; font-size: 0.8rem; outline: none;
    box-sizing: border-box;
  }
  .row input:focus, .row select:focus { border-color: #7c7c9a; }
  .row input:disabled, .row select:disabled { opacity: 0.6; }

  .field-error { display: block; font-size: 0.7rem; color: #f77; margin-top: 2px; }

  /* Type selector dropdown */
  .type-select { width: 100%; min-width: 100px; padding: 0.3rem 0.4rem; background: #2a2a3e; border: 1px solid #444;
    border-radius: 3px; color: #e0e0e0; font-family: monospace; font-size: 0.75rem; outline: none; cursor: pointer; }
  .type-select:focus { border-color: #7c7c9a; }
  .type-select option { background: #1a1a2e; color: #e0e0e0; }
  .type-warning { margin-top: 1px; font-size: 0.65rem; }

  .type-badge { font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; display: inline-block; }
  .type-node { background: #1a3a5a; color: #7cf; }
  .type-literal { background: #2a3a2a; color: #7f7; }
  .type-int { background: #3a2a3a; color: #f7f; }
  .type-float { background: #3a3a1a; color: #ff7; }
  .type-bool { background: #2a2a3a; color: #aaf; }
  .type-url { background: #1a3a3a; color: #7ff; }
  .type-katex { background: #3a1a1a; color: #f77; }

  .btn-icon { background: none; border: none; color: var(--clr-sub); cursor: pointer; padding: 2px 4px; font-size: 0.85rem; }
  .btn-icon:hover { color: #f77; }
  .del-btn { color: #a55; }

  .status-icon { font-size: 0.9rem; }
  .status-icon.created { color: #4f8; }
  .status-icon.duplicate { color: #fa7; }
  .status-icon.error { color: #f77; }

  /* Actions */
  .actions { display: flex; justify-content: flex-end; gap: 8px; padding: 0.5rem 0.75rem; border-top: 1px solid #2a2a3e; background: #1a1a2e; flex-shrink: 0; }

  /* Result view */
  .result-view { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 1rem; height: 100%; padding: 2rem; }
  .result-summary { display: flex; gap: 0.5rem; }
  .result-badge { padding: 0.3rem 0.75rem; border-radius: 4px; font-size: 0.85rem; font-weight: 700; }
  .result-badge.success { background: #1a3a1a; color: #4f8; }
  .result-badge.warning { background: #3a3a1a; color: #fa7; }
  .result-badge.error { background: #3a1a1a; color: #f77; }
  .result-actions { display: flex; gap: 0.5rem; }

  /* Insert dialog */
  .insert-dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .insert-dialog { background: #1a1a2e; border: 1px solid #444; border-radius: 8px; padding: 1rem; display: flex; align-items: center; gap: 0.5rem; }
  .insert-dialog input { width: 80px; padding: 0.3rem 0.5rem; background: #2a2a3e; border: 1px solid #444; border-radius: 3px; color: #e0e0e0; font-family: monospace; }

  /* Confirm dialogs */
  .confirm-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
  .confirm-dialog { background: #1a1a2e; border: 1px solid #444; border-radius: 10px; padding: 1.5rem; max-width: 400px; }
  .confirm-dialog p { margin: 0 0 1rem; color: #e0e0e0; }
  .confirm-actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
</style>
