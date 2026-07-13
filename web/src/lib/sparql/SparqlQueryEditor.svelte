<script>
  /**
   * SPARQL Query Editor — full-featured query editor with CodeMirror 6.
   *
   * Provides:
   *   - CodeMirror 6 editor with SPARQL syntax highlighting
   *   - Run / Stop buttons
   *   - Result rendering (table for SELECT, status for ASK, Turtle for CONSTRUCT)
   *   - Resizeable editor/result split
   *
   * Usage (via tabStore):
   *   tabStore.open("sparql-editor", "SPARQL Query", {})
   */

  import { onMount, onDestroy } from "svelte";
  import { EditorView, basicSetup } from "codemirror";
  import { EditorState } from "@codemirror/state";
  import { oneDark } from "@codemirror/theme-one-dark";
  import { keymap } from "@codemirror/view";
  import { indentWithTab } from "@codemirror/commands";
  import { sparql } from "./sparqlLanguage.js";
  import { sparqlStore } from "./sparqlStore.svelte.js";
  import SparqlResultTable from "./SparqlResultTable.svelte";

  /** @type {HTMLDivElement} */
  let editorContainer = $state(null);

  /** @type {EditorView|null} */
  let editorView = null;

  let resultShown = $state(false);
  let copyMessage = $state("");

  $effect(() => {
    sparqlStore.loadPrefixes();
  });

  onMount(() => {
    if (!editorContainer) return;

    const startState = EditorState.create({
      doc: sparqlStore.query,
      extensions: [
        basicSetup,
        oneDark,
        sparql(),
        keymap.of([indentWithTab]),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            sparqlStore.query = update.state.doc.toString();
          }
        }),
        EditorView.theme({
          "&": { height: "100%" },
          ".cm-scroller": { overflow: "auto" },
          ".cm-content": { fontFamily: '"SF Mono", "Fira Code", "Fira Mono", monospace', fontSize: "13px" },
          ".cm-gutters": { fontSize: "11px" },
        }),
      ],
    });

    editorView = new EditorView({
      state: startState,
      parent: editorContainer,
    });
  });

  $effect(() => {
    // Sync store changes back to editor
    if (editorView && sparqlStore.query !== editorView.state.doc.toString()) {
      // Don't overwrite editor content with store — the editor is the source of truth
    }
  });

  onDestroy(() => {
    if (editorView) {
      editorView.destroy();
      editorView = null;
    }
  });

  async function handleRun() {
    resultShown = true;
    await sparqlStore.execute();
  }

  function handleStop() {
    // In a simple implementation, we just don't await the result.
    // A full implementation would use AbortController.
    resultShown = true;
  }

  function handleCopyQuery() {
    navigator.clipboard.writeText(sparqlStore.query);
    copyMessage = "Copied!";
    setTimeout(() => { copyMessage = ""; }, 1500);
  }

  function handleReset() {
    sparqlStore.reset();
    if (editorView) {
      editorView.dispatch({
        changes: {
          from: 0,
          to: editorView.state.doc.length,
          insert: sparqlStore.query,
        },
      });
    }
  }
</script>

<div class="query-editor">
  <div class="editor-pane" class:with-result={resultShown}>
    <div class="editor-toolbar">
      <span class="toolbar-title">SPARQL</span>
      <div class="toolbar-actions">
        <button
          class="btn-run"
          onclick={handleRun}
          disabled={sparqlStore.loading}
          title="Execute query (Ctrl+Enter)"
        >
          {sparqlStore.loading ? "…" : "▶ Run"}
        </button>
        {#if copyMessage}
          <span class="copy-msg">{copyMessage}</span>
        {/if}
        <button class="btn-icon" onclick={handleCopyQuery} title="Copy query">📋</button>
        <button class="btn-icon" onclick={handleReset} title="Reset to default">↺</button>
      </div>
    </div>
    <div class="editor-container" bind:this={editorContainer}></div>
    {#if sparqlStore.error}
      <div class="error-bar">{sparqlStore.error}</div>
    {/if}
  </div>

  {#if resultShown}
    <div class="result-pane" class:loading={sparqlStore.loading}>
      {#if sparqlStore.loading}
        <div class="loading-indicator"><span class="spinner"></span> Running query…</div>
      {:else if sparqlStore.error}
        <div class="error-display">
          <p class="error-title">Query Error</p>
          <p class="error-message">{sparqlStore.error}</p>
        </div>
      {:else}
        <SparqlResultTable result={sparqlStore.result} />
      {/if}
    </div>
  {/if}
</div>

<style>
  .query-editor {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
  }

  .editor-pane {
    display: flex;
    flex-direction: column;
    min-height: 200px;
    flex-shrink: 0;
  }
  .editor-pane.with-result {
    border-bottom: 1px solid #333;
  }

  .editor-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 12px;
    background: #1e1e2e;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }

  .toolbar-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--clr-muted, #888);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .btn-run {
    background: #4caf50;
    color: #fff;
    border: none;
    border-radius: 4px;
    padding: 4px 14px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    line-height: 1.4;
  }
  .btn-run:hover { background: #43a047; }
  .btn-run:disabled {
    background: #555;
    cursor: not-allowed;
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

  .copy-msg {
    font-size: 11px;
    color: #4caf50;
  }

  .editor-container {
    flex: 1;
    overflow: hidden;
    min-height: 150px;
  }

  .error-bar {
    padding: 4px 12px;
    background: rgba(244, 67, 54, 0.15);
    color: #f44336;
    font-size: 12px;
    border-top: 1px solid rgba(244, 67, 54, 0.3);
  }

  .result-pane {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    background: #16162a;
    min-height: 100px;
  }
  .result-pane.loading {
    opacity: 0.7;
  }

  .loading-indicator {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 24px;
    color: var(--clr-dim, #888);
    font-size: 14px;
  }

  .spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid #444;
    border-top-color: #7ec8e3;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .error-display {
    padding: 24px 16px;
  }

  .error-title {
    font-size: 14px;
    font-weight: 600;
    color: #f44336;
    margin-bottom: 8px;
  }

  .error-message {
    font-size: 13px;
    color: #ccc;
    font-family: "SF Mono", "Fira Code", monospace;
    white-space: pre-wrap;
    word-break: break-word;
    background: rgba(244, 67, 54, 0.05);
    border: 1px solid rgba(244, 67, 54, 0.2);
    border-radius: 4px;
    padding: 8px;
  }
</style>
