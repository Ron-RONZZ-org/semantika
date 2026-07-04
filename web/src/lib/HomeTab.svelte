<script>
  import { onMount } from "svelte";

  let stats = $state(null);

  onMount(async () => {
    try {
      const res = await fetch("/api/v1/graph/nodes");
      const data = await res.json();
      stats = { nodes: data.nodes?.length ?? 0 };
    } catch {
      stats = { nodes: 0 };
    }
  });
</script>

<div class="home">
  <h2>Welcome to Semantika</h2>
  <p>Your personal knowledge graph.</p>
  {#if stats !== null}
    <p class="stats">{stats.nodes} nodes in graph</p>
  {/if}
  <div class="quick-commands">
    <h3>Quick start</h3>
    <ul>
      <li><code>!node add --label "Concept"</code> — create a node</li>
      <li><code>!triple add Subject Predicate Object</code> — add a triple</li>
      <li><code>!ask "What do I know?"</code> — query with natural language</li>
      <li><code>!search keyword</code> — full-text search</li>
    </ul>
  </div>
</div>

<style>
  .home { max-width: 600px; margin: 2rem auto; }
  .stats { color: #666; font-style: italic; }
  .quick-commands { margin-top: 2rem; }
  .quick-commands code { background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 3px; }
</style>
