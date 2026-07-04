<script>
  let { onclose = () => {}, scope = "global" } = $props();
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex a11y_no_static_element_interactions -->
<div class="shortcut-overlay" onclick={onclose} onkeydown={(e) => { if (e.key === 'Escape') onclose(); }} tabindex="0" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="shortcut-box" onclick={(e) => e.stopPropagation()} role="document">
    <h3>Keyboard Shortcuts</h3>
    <div class="shortcut-grid">
      <div class="group">
        <h4>Navigation</h4>
        <div class="item"><kbd>i</kbd> Focus command input</div>
        <div class="item"><kbd>h</kbd> Toggle help</div>
        <div class="item"><kbd>q</kbd> Close current tab</div>
        <div class="item"><kbd>Esc</kbd> Close tab / overlay</div>
      </div>
    </div>
    <button class="close-btn" onclick={onclose}>Close</button>
  </div>
</div>

<style>
  .shortcut-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 200; }
  .shortcut-box { background: #1e1e32; border: 1px solid #444; border-radius: 8px; padding: 1.5rem; max-width: 400px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
  .shortcut-box h3 { margin: 0 0 1rem; font-size: 1rem; color: #e0e0e0; }
  .group { margin-bottom: 1rem; }
  .group h4 { margin: 0 0 0.5rem; font-size: 0.85rem; color: #7c7c9a; text-transform: uppercase; }
  .item { display: flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0; font-size: 0.85rem; color: #e0e0e0; }
  .item kbd { background: #2a2a3e; padding: 0.1rem 0.4rem; border: 1px solid #555; border-radius: 3px; font-family: inherit; font-size: 0.8rem; min-width: 1.5rem; text-align: center; color: #c0c0c0; }
  .close-btn { display: block; margin: 1rem auto 0; padding: 0.4rem 1.5rem; background: #3a6a3a; color: #e0e0e0; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
  .close-btn:hover { background: #4a8a4a; }
</style>
