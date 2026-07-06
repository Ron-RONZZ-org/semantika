<script>
  let { stats = null, compact = false } = $props();
</script>

<div class="brand" class:compact>
  <h1 class="logo">semantika</h1>
  {#if !compact}
    <p class="tagline">Command-driven knowledge graph</p>
  {/if}
</div>

{#if !compact && stats}
  <div class="stats-row">
    <div class="stat"><strong>{stats.nodes}</strong> nodes</div>
    <div class="stat"><strong>{stats.predicates}</strong> predicates</div>
    <div class="stat"><strong>{stats.triples}</strong> triples</div>
  </div>
{/if}

<style>
  .brand {
    text-align: center;
    padding: 3rem 1rem 1rem;
    transition: all 0.4s ease;
    flex-shrink: 0;
  }
  .brand.compact {
    padding: 0.75rem 1rem 0.25rem;
  }
  .logo {
    font-size: 1.6rem;
    font-weight: 300;
    color: #7c7c9a;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-family: monospace;
  }
  .brand.compact .logo {
    font-size: 0.9rem;
    opacity: 0.6;
  }
  .tagline {
    font-size: 0.8rem;
    color: #5a5a7a;
    font-family: monospace;
    margin-top: 0.4rem;
  }
  .stats-row {
    display: flex;
    justify-content: center;
    gap: 1.5rem;
    padding-bottom: 1rem;
    flex-shrink: 0;
  }
  .stat {
    text-align: center;
    font-family: monospace;
    font-size: 0.78rem;
    color: #5a5a7a;
  }
  .stat strong {
    display: block;
    font-size: 1.1rem;
    color: #7c7c9a;
  }
</style>
