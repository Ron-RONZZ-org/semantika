<script>
  import { tick } from "svelte";

  let { message = "Confirm?", onConfirm = () => {}, onDismiss = () => {} } = $props();
  let confirmBtn;
  let overlay;

  $effect(() => { tick().then(() => confirmBtn?.focus()); });

  function trapKeydown(e) {
    if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); onConfirm(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onDismiss(); }
  }
</script>

<div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label="Confirm"
     onclick={onDismiss} onkeydown={trapKeydown} bind:this={overlay} tabindex="0">
  <div class="confirm-box" onclick={(e) => e.stopPropagation()}>
    <p>{message}</p>
    <div class="actions">
      <button class="btn danger" onclick={onConfirm} bind:this={confirmBtn}>Confirm</button>
      <button class="btn" onclick={onDismiss}>Cancel</button>
    </div>
  </div>
</div>

<style>
  .confirm-overlay {
    position: absolute; inset: 0; background: rgba(0,0,0,0.5);
    display: flex; align-items: center; justify-content: center; z-index: 100;
  }
  .confirm-box {
    background: #fff; border: 1px solid #ddd; border-radius: 8px;
    padding: 1.5rem 2rem; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  }
  .confirm-box p { margin-bottom: 1rem; color: #333; font-size: 0.95rem; }
  .actions { display: flex; gap: 0.75rem; justify-content: center; }
  .btn { padding: 0.4rem 1rem; border: 1px solid #ccc; border-radius: 4px;
    background: #f5f5f5; cursor: pointer; font-size: 0.85rem; }
  .btn:hover { background: #e8e8e8; }
  .btn.danger { background: #d32f2f; color: #fff; border-color: #b71c1c; }
  .btn.danger:hover { background: #b71c1c; }
</style>
