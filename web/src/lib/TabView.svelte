<script>
  import { tabStore } from "./tabStore.svelte.js";
  import StatusPopup from "./StatusPopup.svelte";
  import ErrorPopup from "./ErrorPopup.svelte";
  import HelpPopup from "./HelpPopup.svelte";
  import GraphView from "./GraphView.svelte";
  import HomeTab from "./HomeTab.svelte";
  import FormTab from "./FormTab.svelte";

  const active = $derived(tabStore.active);
</script>

<div class="tab-content">
  {#if active.id === "home"}
    <HomeTab />
  {:else if active.type === "graph"}
    <GraphView />
  {:else if active.type === "error"}
    <ErrorPopup data={active.data} />
  {:else if active.type === "help"}
    <HelpPopup />
  {:else if active.type === "form"}
    <FormTab data={active.data} />
  {:else if active.type === "status" || active.type === "table" || active.type === "chat"}
    <StatusPopup data={active.data} />
  {:else}
    <div class="raw"><pre>{JSON.stringify(active.data, null, 2)}</pre></div>
  {/if}
</div>

<style>
  .tab-content { flex: 1; overflow-y: auto; background: #fff; }
  .raw { padding: 1rem; }
  .raw pre { font-size: 0.8rem; overflow-x: auto; }
</style>
