<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { dirtyFormStore } from "./dirtyFormStore.svelte.js";
  import HomeTab from "./HomeTab.svelte";
  import LoadingPopup from "./LoadingPopup.svelte";
  import StatusPopup from "./StatusPopup.svelte";
  import ErrorPopup from "./ErrorPopup.svelte";
  import HelpPopup from "./HelpPopup.svelte";
  import GraphView from "./GraphView.svelte";
  import FormTab from "./FormTab.svelte";
  import QuizPanel from "./QuizPanel.svelte";
  import KeyboardShortcutOverlay from "./KeyboardShortcutOverlay.svelte";
  import NodeListTab from "./NodeListTab.svelte";
  import PredicateListTab from "./PredicateListTab.svelte";
  import TripleListTab from "./TripleListTab.svelte";
  import PromptListTab from "./PromptListTab.svelte";
  import TemplateYamlPopup from "./TemplateYamlPopup.svelte";

  let showGlobalHelp = $state(false);
  let inputFocused = $state(false);

  $effect(() => {
    function handler(e) {
      inputFocused = e.detail.focused;
    }
    window.addEventListener("input-focus-changed", handler);
    return () => window.removeEventListener("input-focus-changed", handler);
  });

  $effect(() => {
    if (tabStore.isHome) {
      requestAnimationFrame(() => {
        document.querySelector(".input-field")?.focus();
      });
    }
  });

  function handleCloseTab(tabId) {
    if (dirtyFormStore.isDirty(tabId)) {
      if (!confirm("You have unsaved changes. Discard them?")) return;
      dirtyFormStore.clear(tabId);
    }
    tabStore.close(tabId);
  }

  function handleKeydown(e) {
    if (e.key === "Escape") {
      const tag = e.target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.target?.isContentEditable) {
        e.target.blur();
        e.preventDefault();
        return;
      }
      if (showGlobalHelp) {
        showGlobalHelp = false;
        e.preventDefault();
        return;
      }
      if (tabStore.isHome && inputFocused) return;
      if (tabStore.active && tabStore.active.closable && !tabStore.isHome) {
        handleCloseTab(tabStore.active.id);
        e.preventDefault();
      } else if (tabStore.isHome) {
        const resultTabs = tabStore.tabs.filter((t) => t.closable);
        if (resultTabs.length > 0) {
          const tab = resultTabs[resultTabs.length - 1];
          handleCloseTab(tab.id);
          e.preventDefault();
        }
      }
      return;
    }

    if (e.key === "h" || e.key === "H") {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable)) {
        return;
      }
      e.preventDefault();
      showGlobalHelp = !showGlobalHelp;
      return;
    }

    if ((e.key === "i" || e.key === "I") && tabStore.isHome) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable)) {
        return;
      }
      e.preventDefault();
      document.querySelector(".input-field")?.focus();
      return;
    }

    if ((e.key === "q" || e.key === "Q") && !tabStore.isHome) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable)) {
        return;
      }
      if (tabStore.active && tabStore.active.closable) {
        handleCloseTab(tabStore.active.id);
      }
      return;
    }

    // Alt+N/P — next/previous tab
    if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
      if (e.key === "n" || e.key === "N") {
        e.preventDefault();
        const idx = tabStore.activeIndex;
        if (idx < tabStore.count - 1) {
          tabStore.setActiveIndex(idx + 1);
        } else {
          tabStore.setActiveIndex(0); // wrap to first
        }
        return;
      }
      if (e.key === "p" || e.key === "P") {
        e.preventDefault();
        const idx = tabStore.activeIndex;
        if (idx > 0) {
          tabStore.setActiveIndex(idx - 1);
        } else {
          tabStore.setActiveIndex(tabStore.count - 1); // wrap to last
        }
        return;
      }
    }

    // Alt+1/2/3/4 — switch to numbered tab
    if (e.altKey && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 9) {
        e.preventDefault();
        tabStore.setActiveIndex(num - 1);
        return;
      }
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="tab-view">
  <div class="tab-content" class:active={tabStore.isHome} role="region" aria-label="Home tab">
    <HomeTab />
  </div>
  {#if tabStore.active && !tabStore.isHome}
    <div class="tab-content" class:active={true} role="region" aria-label="Tab content">
      {#if tabStore.active.type === "loading"}
        <LoadingPopup message={tabStore.active.title} />
      {:else if tabStore.active.type === "status"}
        <StatusPopup data={tabStore.active.data} />
      {:else if tabStore.active.type === "graph"}
        <GraphView />
      {:else if tabStore.active.type === "error"}
        <ErrorPopup data={tabStore.active.data} />
      {:else if tabStore.active.type === "help"}
        <HelpPopup data={tabStore.active.data} />
      {:else if tabStore.active.type === "quiz"}
        <QuizPanel data={tabStore.active.data} />
      {:else if tabStore.active.type === "form"}
        <FormTab data={tabStore.active.data} />
      {:else if tabStore.active.type === "node-list"}
        <NodeListTab data={tabStore.active.data} />
      {:else if tabStore.active.type === "predicate-list"}
        <PredicateListTab data={tabStore.active.data} />
      {:else if tabStore.active.type === "triple-list"}
        <TripleListTab data={tabStore.active.data} />
      {:else if tabStore.active.type === "prompt-list"}
        <PromptListTab data={tabStore.active.data} />
      {:else if tabStore.active.type === "template_yaml"}
        <TemplateYamlPopup data={tabStore.active.data} />
      {:else}
        <StatusPopup data={tabStore.active.data} />
      {/if}
    </div>
  {/if}

  {#if tabStore.count > 1}
    <div class="tab-bar" role="tablist" aria-label="Open tabs">
      {#each tabStore.tabs as tab, i}
        <button
          role="tab"
          class="tab"
          class:active={tab.id === tabStore.active?.id}
          onclick={() => tabStore.setActive(tab.id)}
          aria-selected={tab.id === tabStore.active?.id}
          title={tab.title}
        >
          <span class="tab-icon">{tabIcon(tab.type)}</span>
          <span class="tab-label">{truncate(tab.title, 22)}</span>
          {#if tab.closable}
            <span
              class="tab-close"
              role="button"
              tabindex="-1"
              onclick={(e) => {
                e.stopPropagation();
                handleCloseTab(tab.id);
              }}
              onkeydown={(e) => {
                if (e.key === "Enter") {
                  e.stopPropagation();
                  handleCloseTab(tab.id);
                }
              }}
            >✕</span>
          {/if}
        </button>
      {/each}
      <span class="tab-bar-spacer"></span>
      <span class="tab-hint" title="Keyboard shortcuts">
        {#if tabStore.isHome}
          {#if inputFocused}
            <kbd>Esc</kbd> blur
          {:else}
            <kbd>i</kbd> input mode
          {/if}
          <span class="hint-sep">·</span>
        {/if}
        <kbd>h</kbd> help
        {#if !tabStore.isHome}
          <span class="hint-sep">·</span>
          <kbd>q</kbd> <kbd>Esc</kbd> close
        {/if}
      </span>
    </div>
  {:else}
    <div class="home-hints">
      <span class="tab-hint" title="Keyboard shortcuts">
        {#if inputFocused}
          <kbd>Esc</kbd> blur
        {:else}
          <kbd>i</kbd> input mode
        {/if}
        <span class="hint-sep">·</span>
        <kbd>h</kbd> help
      </span>
    </div>
  {/if}

  {#if showGlobalHelp}
    <KeyboardShortcutOverlay scope="global" onDismiss={() => { showGlobalHelp = false; }} />
  {/if}
</div>

<script module>
  function tabIcon(type) {
    const icons = {
      home: "\u2302",
      status: "\ud83d\udccb",
      "node-list": "\u25c9",
      "predicate-list": "\u25ce",
      "triple-list": "\u25c8",
      graph: "\ud83c\udf10",
      "prompt-list": "\ud83d\udcdd",
      error: "\u26a0",
      help: "?",
      loading: "\u23f3",
      chat: "\ud83d\udcac",
      form: "\u270f",
      quiz: "?",
      template_yaml: "\u2699",
    };
    return icons[type] || "\u2022";
  }

  function truncate(s, max) {
    if (!s) return "";
    return s.length > max ? s.slice(0, max - 1) + "\u2026" : s;
  }
</script>

<style>
  .tab-view {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    height: 100%;
  }
  .tab-content {
    flex: 1;
    overflow: hidden;
    display: none;
    flex-direction: column;
    background: #1a1a2e;
  }
  .tab-content.active {
    display: flex;
  }
  .tab-bar {
    display: flex;
    align-items: stretch;
    background: #16162a;
    border-top: 1px solid #333;
    overflow-x: auto;
    gap: 1px;
    min-height: 32px;
    flex-shrink: 0;
  }
  .tab {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    background: #1a1a2e;
    border: none;
    border-right: 1px solid #333;
    color: var(--clr-sub);
    font-family: monospace;
    font-size: 0.78rem;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s, color 0.1s;
    flex-shrink: 0;
  }
  .tab:hover {
    background: #22223a;
    color: #e0e0e0;
  }
  .tab.active {
    background: #1e1e32;
    color: #e0e0e0;
    border-bottom: 2px solid #7c7c9a;
  }
  .tab-icon {
    font-size: 0.7rem;
    opacity: 0.7;
  }
  .tab-label {
    max-width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .tab-close {
    font-size: 0.65rem;
    padding: 1px 3px;
    border-radius: 3px;
    opacity: 0.5;
    transition: opacity 0.1s;
    line-height: 1;
  }
  .tab-close:hover {
    opacity: 1;
    background: #333;
  }
  .tab-bar-spacer {
    flex: 1;
    background: #1a1a2e;
  }
  .tab-hint {
    display: flex;
    align-items: center;
    gap: 3px;
    padding: 0 8px;
    font-size: 0.68rem;
    color: var(--clr-dim);
    white-space: nowrap;
    flex-shrink: 0;
  }
  .tab-hint kbd {
    display: inline-block;
    padding: 1px 4px;
    font-size: 0.62rem;
    font-family: monospace;
    background: #222;
    border: 1px solid #444;
    border-radius: 3px;
    color: var(--clr-kbd);
  }
  .hint-sep {
    color: #444;
    margin: 0 2px;
  }
  .home-hints {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 4px 0;
    background: #16162a;
    border-top: 1px solid #2a2a3e;
    flex-shrink: 0;
    min-height: 24px;
  }
</style>
