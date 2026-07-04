<script>
  import CommandBar from "./lib/CommandBar.svelte";
  import GraphView from "./lib/GraphView.svelte";
  import ResultPanel from "./lib/ResultPanel.svelte";

  let currentView = $state("graph");
  let resultData = $state(null);
  let resultType = $state("");

  function handleCommand(result) {
    resultType = result.type;
    resultData = result;

    if (result.type === "graph-refresh") {
      // GraphView will refetch
    }
  }
</script>

<div id="semantika-app">
  <header>
    <div class="header-top">
      <h1>Semantika</h1>
      <nav class="tabs">
        <button class:active={currentView === "graph"} onclick={() => currentView = "graph"}>
          Graph
        </button>
        <button class:active={currentView === "search"} onclick={() => currentView = "search"}>
          Search
        </button>
      </nav>
    </div>
    <CommandBar oncommand={handleCommand} />
  </header>

  <main>
    {#if currentView === "graph"}
      <GraphView refresh={resultType === "graph-refresh"} />
    {/if}
    {#if resultData}
      <ResultPanel data={resultData} />
    {/if}
  </main>
</div>

<style>
  #semantika-app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  header {
    border-bottom: 1px solid #ddd;
    padding: 0.5rem 1rem;
    background: #fafafa;
  }
  .header-top {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.5rem;
  }
  h1 {
    font-size: 1.2rem;
    margin: 0;
  }
  nav.tabs {
    display: flex;
    gap: 0.25rem;
  }
  nav.tabs button {
    padding: 0.25rem 0.75rem;
    border: 1px solid #ccc;
    background: #fff;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
  }
  nav.tabs button.active {
    background: #4a90d9;
    color: #fff;
    border-color: #4a90d9;
  }
  main {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
</style>
