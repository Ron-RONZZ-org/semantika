<script>
  import CommandBar from "./lib/CommandBar.svelte";
  import HomeTab from "./lib/HomeTab.svelte";

  let page = $state("home");
</script>

<div id="semantika-app">
  <header>
    <h1>Semantika</h1>
    <CommandBar />
  </header>
  <main>
    {#if page === "home"}
      <HomeTab />
    {:else if page === "graph"}
      <p>Graph view — coming soon</p>
    {:else if page === "search"}
      <p>Search — coming soon</p>
    {/if}
  </main>
</div>

<style>
  #semantika-app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  header {
    border-bottom: 1px solid #ddd;
    padding: 0.5rem 1rem;
  }
  header h1 {
    margin: 0 0 0.5rem 0;
    font-size: 1.2rem;
  }
  main {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }
</style>
