<script>
  let { data } = $props();
</script>

<div class="error-popup">
  <span class="icon">⚠</span>
  <span class="msg">{data?.message || "Unknown error"}</span>
</div>

<style>
  .error-popup {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 1rem; margin: 1rem;
    background: #fbe9e7; color: #d32f2f;
    border: 1px solid #ef9a9a; border-radius: 6px;
    font-size: 0.9rem;
  }
  .icon { font-size: 1.2rem; }
</style>
