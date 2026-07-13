<script>
  import { commandTree } from "./commandTree.js";
  import { getCompletions, getPromptCompletions } from "./commandEngine.js";
  import { history } from "./commandHistory.svelte.js";

  let {
    onSubmit,
    placeholder = 'Type !command, search, or ask anything\u2026',
    centered = true,
  } = $props();

  let value = $state("");
  let suggestions = $state([]);
  let hints = $state([]);
  let dataCompletions = $state([]);
  let positionals = $state([]);
  let selectedSuggestion = $state(-1);
  let selectedDataIndex = $state(-1);
  let isCommandMode = $state(false);
  let isPromptCommand = $state(false);
  let textareaEl = $state(null);

  let hasInteractiveItems = $derived(
    suggestions.length > 0 || dataCompletions.length > 0,
  );

  let showSuggestions = $derived(
    ((isCommandMode || isPromptCommand) && hasInteractiveItems) || positionals.length > 0,
  );

  let displaySuggestions = $derived(
    dataCompletions.length > 0 ? [] : suggestions,
  );
  let displayHints = $derived(
    dataCompletions.length > 0 ? [] : hints,
  );

  function checkCommandMode() {
    isCommandMode = value.startsWith("!");
    isPromptCommand = value.startsWith("/") && !value.startsWith("//");
    if (!isCommandMode && !isPromptCommand) {
      suggestions = [];
      hints = [];
      dataCompletions = [];
      positionals = [];
    }
  }

  function updateSuggestions() {
    if (isPromptCommand) {
      const result = getPromptCompletions(value);
      suggestions = result.completions;
      hints = result.hints;
      dataCompletions = [];
      positionals = [];
      selectedSuggestion = -1;
      selectedDataIndex = -1;
      return;
    }
    if (!isCommandMode) {
      suggestions = [];
      hints = [];
      dataCompletions = [];
      positionals = [];
      selectedSuggestion = -1;
      selectedDataIndex = -1;
      return;
    }
    const result = getCompletions(value);
    suggestions = result.completions;
    hints = result.hints;
    positionals = result.positionals;
    selectedSuggestion = -1;
    selectedDataIndex = -1;

    dataCompletions = [];
  }

  function countCommandTokens(tokens) {
    let current = commandTree;
    for (let i = 0; i < tokens.length; i++) {
      const found = current.find((n) => n.name.toLowerCase() === tokens[i].toLowerCase());
      if (!found) return i;
      if (!found.children || found.children.length === 0) return i + 1;
      current = found.children || [];
    }
    return tokens.length;
  }

  function autoResize() {
    if (!textareaEl) return;
    textareaEl.style.height = "auto";
    textareaEl.style.height = Math.min(textareaEl.scrollHeight, 200) + "px";
  }

  function handleInput() {
    autoResize();
    checkCommandMode();
    if (isCommandMode || isPromptCommand) updateSuggestions();
  }

  function getDataValue(dc) {
    return dc.value || dc.uuid?.slice(0, 8) || "";
  }

  function getDataLabel(dc) {
    return dc.value || dc.uuid?.slice(0, 8) || "";
  }

  function applyCompletion(completion) {
    if (!completion) return;
    if (value.endsWith(" ")) {
      value = value + completion + " ";
    } else if (completion.startsWith("!") && value.startsWith("!")) {
      value = completion + " ";
    } else {
      // Replace the last token using regex to handle edge cases (multiple spaces, trailing spaces)
      value = value.replace(/\S+$/, completion) + " ";
    }
    suggestions = [];
    hints = [];
    dataCompletions = [];
    positionals = [];
    selectedSuggestion = -1;
    selectedDataIndex = -1;
    requestAnimationFrame(() => updateSuggestions());
  }

  function handleKeydown(e) {
    if (e.key === "Escape") {
      if (showSuggestions) {
        suggestions = [];
        hints = [];
        dataCompletions = [];
        positionals = [];
        return;
      }
      textareaEl?.blur();
      e.stopPropagation();
      return;
    }

    if (e.key === "Tab" && hasInteractiveItems) {
      e.preventDefault();
      if (displaySuggestions.length > 0) {
        const idx = selectedSuggestion >= 0 ? selectedSuggestion : 0;
        applyCompletion(displaySuggestions[idx]);
      } else if (dataCompletions.length > 0) {
        const idx = selectedDataIndex >= 0 ? selectedDataIndex : 0;
        applyCompletion(getDataValue(dataCompletions[idx]));
      }
      return;
    }

    if (e.key === "ArrowUp") {
      if (hasInteractiveItems) {
        e.preventDefault();
        if (dataCompletions.length > 0 && displaySuggestions.length === 0) {
          selectedDataIndex = Math.max(0, selectedDataIndex - 1);
        } else if (displaySuggestions.length > 0) {
          selectedSuggestion = Math.max(0, selectedSuggestion - 1);
        }
        return;
      }
      e.preventDefault();
      const cmd = history.back();
      if (cmd) {
        value = cmd;
        checkCommandMode();
        requestAnimationFrame(() => updateSuggestions());
      }
      return;
    }

    if (e.key === "ArrowDown") {
      if (hasInteractiveItems) {
        e.preventDefault();
        if (dataCompletions.length > 0 && displaySuggestions.length === 0) {
          selectedDataIndex = Math.min(dataCompletions.length - 1, selectedDataIndex + 1);
        } else if (displaySuggestions.length > 0) {
          selectedSuggestion = Math.min(displaySuggestions.length - 1, selectedSuggestion + 1);
        }
        return;
      }
      e.preventDefault();
      const cmd = history.forward();
      value = cmd;
      checkCommandMode();
      requestAnimationFrame(() => updateSuggestions());
      return;
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const cmd = value.trim();
      if (!cmd) return;

      // ── Completion fill mode: fill input on Enter when suggestions are visible ──
      if (displaySuggestions.length > 0) {
        const idx = selectedSuggestion >= 0 ? selectedSuggestion : 0;
        const completion = displaySuggestions[idx];
        const lastToken = cmd.split(/\s+/).pop() || "";
        if (completion.toLowerCase() !== lastToken.toLowerCase()) {
          applyCompletion(completion);
          // After filling, if the completed command path has no more children
          // (i.e. it's a leaf command), submit immediately.
          const newCmd = value.trim();
          const { completions: nextCompletions } = getCompletions(newCmd);
          const isLeaf = nextCompletions.length === 0;
          // For !sparql specifically, always submit after completing "query"
          const isSparqlQuery = /^!sparql\s+query\s*$/i.test(newCmd);
          if (isLeaf || isSparqlQuery) {
            // Submit the now-completed command
            history.push(newCmd);
            value = "";
            suggestions = [];
            hints = [];
            dataCompletions = [];
            positionals = [];
            if (onSubmit) onSubmit(newCmd);
          }
          return;
        }
        // Completion is the same as what's already typed → clear suggestions and submit.
        suggestions = [];
        hints = [];
        dataCompletions = [];
        positionals = [];
      }
      if (dataCompletions.length > 0) {
        const idx = selectedDataIndex >= 0 ? selectedDataIndex : 0;
        const completion = getDataValue(dataCompletions[idx]);
        const lastToken = cmd.split(/\s+/).pop() || "";
        if (completion.toLowerCase() !== lastToken.toLowerCase()) {
          applyCompletion(completion);
          return;
        }
        // Same token → fall through to submit.
      }
      // No completions or completion is already typed → submit.

      history.push(cmd);
      value = "";
      suggestions = [];
      hints = [];
      dataCompletions = [];
      positionals = [];
      if (onSubmit) onSubmit(cmd);
    }
  }

  function handleFocus() {
    window.dispatchEvent(new CustomEvent("input-focus-changed", { detail: { focused: true } }));
  }

  function handleBlur() {
    window.dispatchEvent(new CustomEvent("input-focus-changed", { detail: { focused: false } }));
  }
</script>

<div class="chat-input" class:centered>
  <div class="input-area">
    <!-- svelte-ignore a11y_autofocus -->
    <textarea
      bind:this={textareaEl}
      class="input-field"
      class:command-mode={isCommandMode}
      {placeholder}
      bind:value
      oninput={handleInput}
      onkeydown={handleKeydown}
      onfocus={handleFocus}
      onblur={handleBlur}
      aria-label="Message input"
      autofocus
    ></textarea>
  </div>

  {#if showSuggestions}
    <div class="suggestions">
      {#if positionals.length > 0}
        <div class="positional-tracker" aria-hidden="true">
          {#each positionals as p, i}
            <span class="pos-arg" class:entered={p.entered} class:pending={!p.entered}>
              {p.entered ? p.name : `<${p.name}>`}
            </span>
            {#if !p.entered && p.required}
              <span class="pos-required" aria-hidden="true">*</span>
            {/if}
            {#if i < positionals.length - 1}
              <span class="pos-sep"> </span>
            {/if}
          {/each}
        </div>
      {/if}

      {#each displaySuggestions as suggestion, i}
        <button
          class="suggestion"
          class:selected={i === selectedSuggestion}
          onmousedown={(e) => {
            e.preventDefault();
            applyCompletion(suggestion);
          }}
        >
          <span class="suggestion-text">{suggestion}</span>
          {#if displayHints[i]}
            <span class="hint-text">{displayHints[i]}</span>
          {/if}
        </button>
      {/each}

      {#each dataCompletions as dc, i}
        <button
          class="suggestion"
          class:selected={i === selectedDataIndex}
          onmousedown={(e) => {
            e.preventDefault();
            applyCompletion(getDataValue(dc));
          }}
        >
          <span class="suggestion-text">{getDataLabel(dc)}</span>
          <span class="hint-text">{dc.value ? "" : dc.label}</span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .chat-input {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    width: 100%;
    max-width: 720px;
    margin: 0 auto;
    transition: all 0.3s ease;
  }
  .chat-input.centered {
    justify-content: center;
    flex: 1;
  }
  .input-area {
    position: relative;
    width: 100%;
    display: flex;
    align-items: flex-end;
    gap: 0.5rem;
  }
  .input-field {
    flex: 1;
    background: #1e1e32;
    border: 1px solid #555;
    border-radius: 14px;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 0.95rem;
    padding: 0.85rem 1rem;
    outline: none;
    resize: none;
    line-height: 1.6;
    min-height: 52px;
    max-height: 200px;
    overflow-y: auto;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .input-field:focus {
    border-color: #7c7c9a;
    box-shadow: 0 0 0 2px rgba(124, 124, 154, 0.2);
  }
  .input-field.command-mode {
    border-color: #5a8a5a;
    box-shadow: 0 0 0 2px rgba(90, 138, 90, 0.15);
  }
  .input-field::placeholder {
    color: #555;
  }
  .suggestions {
    width: 100%;
    max-height: 200px;
    overflow-y: auto;
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 8px;
    margin-top: 4px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
    z-index: 100;
  }
  .positional-tracker {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.35rem 0.75rem;
    background: #16162a;
    border-bottom: 1px solid #333;
    font-family: monospace;
    font-size: 0.8rem;
    user-select: none;
    pointer-events: none;
  }
  .pos-arg {
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
  }
  .pos-arg.entered {
    color: #c0c0e0;
    font-weight: 500;
  }
  .pos-arg.pending {
    color: #5a5a7a;
  }
  .pos-required {
    color: #c44;
    font-size: 0.7rem;
    margin-left: 0;
  }
  .pos-sep {
    color: #444;
  }
  .suggestion {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 0.4rem 0.75rem;
    background: transparent;
    border: none;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    text-align: left;
  }
  .suggestion:hover,
  .suggestion.selected {
    background: #2a2a44;
  }
  .hint-text {
    color: #7c7c9a;
    font-size: 0.75rem;
    margin-left: 1rem;
    flex-shrink: 0;
  }
</style>
