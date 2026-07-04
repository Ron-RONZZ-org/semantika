<script>
  import { onMount } from "svelte";

  let commands = $state([]);

  onMount(async () => {
    try {
      const res = await fetch("/api/v1/command/help");
      const data = await res.json();
      commands = data.commands || [];
    } catch { commands = []; }
  });
</script>

<div class="help">
  <h3>Commands</h3>
  <table>
    <thead><tr><th>Command</th><th>Description</th></tr></thead>
    <tbody>
      {#each commands as c}
        <tr><td><code>{c.cmd}</code></td><td>{c.desc}</td></tr>
      {/each}
    </tbody>
  </table>
  <p class="tip">Type any command in the bar above, or just ask naturally!</p>
</div>

<style>
  .help { padding: 1rem; }
  .help h3 { margin: 0 0 0.5rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { padding: 0.3rem 0.5rem; border: 1px solid #ddd; text-align: left; }
  th { background: #f5f5f5; }
  code { background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.8rem; }
  .tip { margin-top: 1rem; color: #888; font-style: italic; font-size: 0.85rem; }
</style>
