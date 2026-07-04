<script>
  import { onMount } from "svelte";
  import { tabs, activeTabId, closeTab, openTab } from "./lib/tabStore.js";
  import { initCommandTree } from "./lib/commandTree.js";
  import CommandBar from "./lib/CommandBar.svelte";
  import TabView from "./lib/TabView.svelte";

  let loading = $state(true);
  let error = $state(null);

  onMount(async () => {
    try {
      await initCommandTree();
      loading = false;
    } catch (err) {
      error = String(err);
      loading = false;
    }
  });

  function handleCommand(result) {
    if (!result) return;
    if (result.type === "error") {
      openTab("error", "Error", result);
    } else if (result.type === "status") {
      openTab("status", "Result", result);
    } else if (result.type === "table") {
      openTab("table", result.label || "Results", result);
    } else if (result.type === "chat") {
      openTab("chat", "Chat", result);
    } else if (result.type === "graph-refresh") {
      // handled by GraphView
    } else {
      openTab("status", "Result", result);
    }
  }
</script>

<div id="semantika-app">
  <header>
    <div class="header-row">
      <h1>Semantika</h1>
      <span class="subtitle">knowledge graph</span>
      <span class="shortcuts">Tab/` navigate · Ctrl+K command · ? help</span>
    </div>
    <CommandBar oncommand={handleCommand} />
  </header>

  {#if loading}
    <div class="loading-screen">Loading…</div>
  {:else if error}
    <div class="error-screen">⚠ {error}</div>
  {:else}
    <TabView />
  {/if}

  <footer class="tab-bar">
    <button class="tab-btn home-btn" class:active={$activeTabId === "home"}
      onclick={() => activeTabId.set("home")}>🏠 Home</button>
    {#each $tabs as tab (tab.id)}
      <button class="tab-btn" class:active={$activeTabId === tab.id}
        onclick={() => activeTabId.set(tab.id)}>
        {tab.title || tab.type}
        {#if tab.closable}
          <span class="tab-close" onclick={(e) => { e.stopPropagation(); closeTab(tab.id); }}>✕</span>
        {/if}
      </button>
    {/each}
  </footer>
</div>

<style>
  #semantika-app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f5f5f5;
  }
  header {
    background: #fff;
    border-bottom: 1px solid #ddd;
    padding: 0.4rem 1rem;
    flex-shrink: 0;
  }
  .header-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.4rem;
  }
  h1 { margin: 0; font-size: 1.1rem; font-weight: 700; }
  .subtitle { color: #888; font-size: 0.8rem; }
  .shortcuts { margin-left: auto; color: #aaa; font-size: 0.75rem; }
  .loading-screen, .error-screen {
    flex: 1; display: flex; align-items: center; justify-content: center;
    color: #999; font-size: 1.1rem;
  }
  .error-screen { color: #d32f2f; }
  .tab-bar {
    display: flex;
    gap: 2px;
    padding: 2px 4px;
    background: #e8e8e8;
    border-top: 1px solid #ccc;
    overflow-x: auto;
    flex-shrink: 0;
  }
  .tab-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border: none;
    background: #ddd;
    border-radius: 4px 4px 0 0;
    cursor: pointer;
    font-size: 0.8rem;
    white-space: nowrap;
  }
  .tab-btn.active { background: #fff; font-weight: 600; }
  .tab-close {
    margin-left: 4px;
    padding: 0 2px;
    border-radius: 2px;
    cursor: pointer;
    font-size: 0.7rem;
  }
  .tab-close:hover { background: #ccc; }
  .home-btn { font-weight: 600; }
</style>
