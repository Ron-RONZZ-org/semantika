<script>
  let query = $state("");
  let results = $state([]);

  async function search() {
    if (!query.trim()) return;
    try {
      const res = await fetch(`/api/v1/query/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      results = data.results ?? [];
    } catch {
      results = [];
    }
  }
</script>

<div class="search-tab">
  <input type="text" bind:value={query} placeholder="Search nodes, predicates, triples…" oninput={search} />
  <div class="results">
    {#each results as result}
      <div class="result-item">{JSON.stringify(result)}</div>
    {/each}
  </div>
</div>
