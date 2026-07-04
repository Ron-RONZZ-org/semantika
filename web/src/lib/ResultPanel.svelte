<script>
  let { data = null } = $props();

  function renderValue(val) {
    if (typeof val === "object" && val !== null) {
      return JSON.stringify(val, null, 2);
    }
    return String(val);
  }
</script>

{#if data}
  <div class="result-panel">
    {#if data.type === "error"}
      <div class="error">⚠ {data.message || "Unknown error"}</div>

    {:else if data.type === "status"}
      <div class="status">
        <pre>{renderValue(data.data || data)}</pre>
      </div>

    {:else if data.type === "table"}
      <div class="table-result">
        {#if data.label}<h3>{data.label}</h3>{/if}
        {#if data.data && data.data.length > 0}
          <table>
            <thead>
              <tr>
                {#each Object.keys(data.data[0]) as col}
                  <th>{col}</th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each data.data as row}
                <tr>
                  {#each Object.values(row) as val}
                    <td>{renderValue(val)}</td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <p class="empty">No results.</p>
        {/if}
      </div>

    {:else if data.type === "graph-refresh"}
      <p class="info">Graph refreshed.</p>

    {:else}
      <pre>{JSON.stringify(data, null, 2)}</pre>
    {/if}
  </div>
{/if}

<style>
  .result-panel {
    max-height: 40vh;
    overflow-y: auto;
    padding: 1rem;
    border-top: 1px solid #eee;
    background: #fff;
  }
  .error {
    color: #d32f2f;
    background: #fbe9e7;
    padding: 0.75rem;
    border-radius: 4px;
  }
  .status pre {
    white-space: pre-wrap;
    font-size: 0.85rem;
    background: #f5f5f5;
    padding: 0.75rem;
    border-radius: 4px;
  }
  .table-result h3 {
    margin: 0 0 0.5rem;
    font-size: 0.95rem;
  }
  .table-result table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }
  .table-result th, .table-result td {
    padding: 0.4rem 0.6rem;
    border: 1px solid #ddd;
    text-align: left;
  }
  .table-result th {
    background: #f5f5f5;
    font-weight: 600;
  }
  .empty, .info {
    color: #999;
    font-style: italic;
    padding: 1rem;
  }
</style>
