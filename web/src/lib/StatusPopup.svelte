<script>
  let { data } = $props();

  function renderValue(val) {
    if (val === null || val === undefined) return "";
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  }
</script>

<div class="status-popup">
  {#if data?.data}
    {#if data.type === "table" && Array.isArray(data.data)}
      {#if data.data.length > 0}
        <table>
          <thead>
            <tr>
              {#each Object.keys(data.data[0]).filter(k => !k.startsWith("_")) as col}
                <th>{col}</th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each data.data as row}
              <tr>
                {#each Object.entries(row) as [key, val]}
                  {#if !key.startsWith("_")}
                    <td>{renderValue(val)}</td>
                  {/if}
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <p class="empty">No results.</p>
      {/if}
    {:else}
      {#each Object.entries(data.data) as [key, val]}
        <div class="kv">
          <span class="key">{key}</span>
          <span class="val">{renderValue(val)}</span>
        </div>
      {/each}
    {/if}
  {:else}
    <pre>{JSON.stringify(data, null, 2)}</pre>
  {/if}
</div>

<style>
  .status-popup { padding: 1rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { padding: 0.3rem 0.5rem; border: 1px solid #ddd; text-align: left; }
  th { background: #f5f5f5; font-weight: 600; }
  .kv { display: flex; gap: 0.5rem; padding: 0.3rem 0; border-bottom: 1px solid #eee; }
  .key { font-weight: 600; color: #555; min-width: 120px; font-size: 0.85rem; }
  .val { color: #333; font-size: 0.85rem; }
  .empty { color: #999; font-style: italic; padding: 1rem; text-align: center; }
</style>
