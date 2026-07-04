<script>
  import { onMount } from "svelte";
  import { tabStore } from "./lib/tabStore.svelte.js";
  import { initCommandTree } from "./lib/commandTree.js";
  import { getAllShortcuts } from "./lib/keyboardShortcuts.svelte.js";
  import CommandBar from "./lib/CommandBar.svelte";
  import TabView from "./lib/TabView.svelte";
  import KeyboardShortcutOverlay from "./lib/KeyboardShortcutOverlay.svelte";

  let loading = $state(true);
  let showShortcuts = $state(false);

  onMount(async () => {
    try {
      await initCommandTree();
    } catch { /* ignore */ }
    loading = false;
  });

  function handleCommand(result) {
    if (!result) return;
    const type = result.type || "status";
    const title = result.title || (type === "error" ? "Error" : "Result");
    tabStore.open(type, title, result);
  }

  function handleGlobalKeydown(e) {
    if (e.target?.tagName === "INPUT" || e.target?.tagName === "TEXTAREA") return;
    if (e.key === "h" && !e.ctrlKey && !e.metaKey) { showShortcuts = !showShortcuts; e.preventDefault(); }
    if (e.key === "i" && !e.ctrlKey && !e.metaKey) {
      document.querySelector(".command-bar input")?.focus();
      e.preventDefault();
    }
    if (e.key === "q" && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
      const active = tabStore.active;
      if (active && active.closable) tabStore.close(active.id);
      e.preventDefault();
    }
    if (e.key === "Escape") {
      if (showShortcuts) { showShortcuts = false; e.preventDefault(); return; }
      const active = tabStore.active;
      if (active && active.closable && active.id !== "home") {
        tabStore.close(active.id); e.preventDefault();
      }
    }
  }
</script>

<svelte:window onkeydown={handleGlobalKeydown} />

<div id="semantika-app">
  <header>
    <div class="header-row">
      <h1>Semantika</h1>
      <span class="subtitle">knowledge graph</span>
      <span class="shortcuts"><kbd>i</kbd> focus · <kbd>h</kbd> help · <kbd>q</kbd> close</span>
    </div>
    <CommandBar oncommand={handleCommand} />
  </header>

  {#if loading}
    <div class="loading-screen">Loading…</div>
  {:else}
    <TabView />
  {/if}

  {#if showShortcuts}
    <KeyboardShortcutOverlay onclose={() => showShortcuts = false} />
  {/if}

  <footer class="tab-bar">
    <button class="tab-btn home-btn" class:active={tabStore.isHome}
      onclick={() => tabStore.goHome()}>🏠 Home</button>
    {#each tabStore.tabs as tab (tab.id)}
      {#if tab.id !== "home"}
        <button class="tab-btn" class:active={tabStore.active.id === tab.id}
          onclick={() => tabStore.setActive(tab.id)}>
          {tab.title || tab.type}
          {#if tab.closable}
            <span class="tab-close" onclick={(e) => { e.stopPropagation(); tabStore.close(tab.id); }}>✕</span>
          {/if}
        </button>
      {/if}
    {/each}
  </footer>
</div>

<style>
  #semantika-app { display: flex; flex-direction: column; height: 100vh; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; }
  header { background: #fff; border-bottom: 1px solid #ddd; padding: 0.4rem 1rem; flex-shrink: 0; }
  .header-row { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem; }
  h1 { margin: 0; font-size: 1.1rem; font-weight: 700; }
  .subtitle { color: #888; font-size: 0.8rem; }
  .shortcuts { margin-left: auto; color: #aaa; font-size: 0.75rem; }
  .shortcuts kbd { background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 2px; border: 1px solid #ddd; font-family: inherit; }
  .loading-screen { flex: 1; display: flex; align-items: center; justify-content: center; color: #999; }
  .tab-bar { display: flex; gap: 2px; padding: 2px 4px; background: #e8e8e8; border-top: 1px solid #ccc; overflow-x: auto; flex-shrink: 0; }
  .tab-btn { display: flex; align-items: center; gap: 4px; padding: 4px 10px; border: none; background: #ddd; border-radius: 4px 4px 0 0; cursor: pointer; font-size: 0.8rem; white-space: nowrap; }
  .tab-btn.active { background: #fff; font-weight: 600; }
  .tab-btn:hover { background: #eee; }
  .tab-close { margin-left: 4px; padding: 0 2px; border-radius: 2px; cursor: pointer; font-size: 0.7rem; }
  .tab-close:hover { background: #ccc; }
  .home-btn { font-weight: 600; }
</style>
