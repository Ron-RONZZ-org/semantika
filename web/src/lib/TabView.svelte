<script>
  import { tabs, activeTabId } from "./tabStore.js";
  import StatusPopup from "./StatusPopup.svelte";
  import ErrorPopup from "./ErrorPopup.svelte";
  import HelpPopup from "./HelpPopup.svelte";
  import GraphView from "./GraphView.svelte";
  import HomeTab from "./HomeTab.svelte";
</script>

<div class="tab-content">
  {#each $tabs as tab (tab.id)}
    <div class="tab-pane" class:active={$activeTabId === tab.id}>
      {#if $activeTabId === tab.id}
        {#if tab.type === "home" || tab.id === "home"}
          <HomeTab />
        {:else if tab.type === "graph"}
          <GraphView />
        {:else if tab.type === "error"}
          <ErrorPopup data={tab.data} />
        {:else if tab.type === "help"}
          <HelpPopup />
        {:else if tab.type === "status" || tab.type === "table"}
          <StatusPopup data={tab.data} />
        {:else if tab.type === "chat"}
          <div class="chat-result">
            {#if tab.data?.data?.reply}
              <div class="chat-reply">{@html tab.data.data.reply.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>')}</div>
            {:else}
              <pre>{JSON.stringify(tab.data, null, 2)}</pre>
            {/if}
          </div>
        {:else}
          <pre>{JSON.stringify(tab.data, null, 2)}</pre>
        {/if}
      {/if}
    </div>
  {:else}
    <div class="tab-pane active">
      <HomeTab />
    </div>
  {/each}
</div>

<style>
  .tab-content { flex: 1; overflow-y: auto; position: relative; }
  .tab-pane { display: none; height: 100%; }
  .tab-pane.active { display: block; }
  .chat-result { padding: 1rem; }
  .chat-reply { line-height: 1.6; font-size: 0.95rem; }
  :global(.tab-pane pre) {
    padding: 1rem;
    font-size: 0.8rem;
    overflow-x: auto;
  }
</style>
