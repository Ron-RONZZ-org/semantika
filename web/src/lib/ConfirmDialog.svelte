<script>
  import { tick } from "svelte";

  let {
    message = "Confirm?",
    onConfirm = () => {},
    onDismiss = () => {},
    onFeedback = null,
  } = $props();

  let confirmBtn;
  let overlay;
  let showFeedback = $state(false);
  let feedbackText = $state("");

  $effect(() => { tick().then(() => confirmBtn?.focus()); });

  function trapKeydown(e) {
    if (e.key === "Enter" && !showFeedback) {
      e.preventDefault(); e.stopPropagation(); onConfirm();
    } else if (e.key === "Escape" && !showFeedback) {
      e.preventDefault(); e.stopPropagation(); handleDismiss();
    }
  }

  function handleDismiss() {
    if (onFeedback) {
      showFeedback = true;
      setTimeout(() => {
        const el = document.querySelector(".feedback-input");
        if (el) el.focus();
      }, 50);
    } else {
      onDismiss();
    }
  }

  function handleSendFeedback() {
    if (feedbackText.trim()) {
      onFeedback(feedbackText.trim());
      feedbackText = "";
      showFeedback = false;
    }
  }

  function handleSkipFeedback() {
    showFeedback = false;
    onDismiss();
  }
</script>

<div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label="Confirm"
     onclick={showFeedback ? () => {} : handleDismiss}
     onkeydown={trapKeydown} bind:this={overlay} tabindex="0">
  <div class="confirm-box" onclick={(e) => e.stopPropagation()}>
    {#if showFeedback}
      <p class="feedback-heading">What would you like to do instead?</p>
      <textarea
        class="feedback-input"
        bind:value={feedbackText}
        placeholder="e.g. search first, list existing items, try a different approach\u2026"
        rows="2"
      ></textarea>
      <div class="actions">
        <button class="btn primary" onclick={handleSendFeedback} disabled={!feedbackText.trim()}>
          Send
        </button>
        <button class="btn" onclick={handleSkipFeedback}>Skip</button>
      </div>
    {:else}
      <p>{message}</p>
      <div class="actions">
        <button class="btn danger" onclick={onConfirm} bind:this={confirmBtn}>Confirm</button>
        <button class="btn" onclick={handleDismiss}>
          {onFeedback ? "Tell LLM what to do instead\u2026" : "Cancel"}
        </button>
      </div>
    {/if}
  </div>
</div>

<style>
  .confirm-overlay {
    position: absolute; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center; z-index: 100;
  }
  .confirm-box {
    background: #1e1e32; border: 1px solid #444; border-radius: 8px;
    padding: 1.5rem 2rem; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    max-width: 480px;
  }
  .confirm-box p { margin-bottom: 1rem; color: #e0e0e0; font-size: 0.95rem; line-height: 1.4; }
  .actions { display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap; }
  .btn {
    padding: 0.4rem 1rem; border: 1px solid #555; border-radius: 4px;
    background: #2a2a3e; color: #e0e0e0; cursor: pointer; font-size: 0.85rem; }
  .btn:hover { background: #3a3a5a; }
  .btn.danger { background: #5a2a2a; color: #e0e0e0; border-color: #7a3a3a; }
  .btn.danger:hover { background: #7a3a3a; }
  .btn.primary { background: #2a4a5a; color: #e0e0e0; border-color: #3a6a7a; }
  .btn.primary:hover { background: #3a5a6a; }
  .btn:disabled { opacity: 0.4; cursor: default; }

  .feedback-heading {
    font-size: 0.9rem;
    color: #b0b0c0;
    margin-bottom: 0.5rem;
  }
  .feedback-input {
    width: 100%;
    box-sizing: border-box;
    background: #2a2a3e;
    border: 1px solid #555;
    border-radius: 6px;
    padding: 0.5rem 0.7rem;
    color: #e0e0e0;
    font-family: inherit;
    font-size: 0.85rem;
    resize: none;
    outline: none;
    margin-bottom: 0.75rem;
  }
  .feedback-input:focus {
    border-color: #7c7c9a;
  }
</style>
