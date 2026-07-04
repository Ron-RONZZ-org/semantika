<script>
  let { data = {} } = $props();
</script>

<div class="error">
  <p class="message">{data.message || "An error occurred."}</p>
  {#if data.suggestion}
    <p class="suggestion">{data.suggestion}</p>
  {/if}
</div>

<style>
  .error {
    text-align: center;
    padding: 1.5rem;
  }
  .message {
    color: #e74c3c;
    font-family: monospace;
    font-size: 0.9rem;
    margin-bottom: 0.75rem;
  }
  .suggestion {
    color: #7c7c9a;
    font-family: monospace;
    font-size: 0.85rem;
    background: #2a2a3e;
    padding: 0.5rem;
    border-radius: 4px;
  }
</style>
