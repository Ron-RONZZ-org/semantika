<script>
  let { onclose = () => {} } = $props();
</script>

<div class="shortcut-overlay" onclick={onclose} onkeydown={(e) => { if (e.key === 'Escape') onclose(); }} tabindex="0">
  <div class="shortcut-box" onclick={(e) => e.stopPropagation()}>
    <h3>Keyboard Shortcuts</h3>
    <div class="shortcut-grid">
      <div class="group">
        <h4>Navigation</h4>
        <div class="item"><kbd>i</kbd> Focus command input</div>
        <div class="item"><kbd>h</kbd> Toggle shortcuts</div>
        <div class="item"><kbd>q</kbd> Close current tab</div>
        <div class="item"><kbd>Esc</kbd> Close tab / overlay</div>
      </div>
    </div>
    <button class="close-btn" onclick={onclose}>Close</button>
  </div>
</div>

<style>
  .shortcut-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 200; }
  .shortcut-box { background: #fff; border-radius: 8px; padding: 1.5rem; max-width: 400px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.2); }
  .shortcut-box h3 { margin: 0 0 1rem; font-size: 1rem; }
  .group { margin-bottom: 1rem; }
  .group h4 { margin: 0 0 0.5rem; font-size: 0.85rem; color: #666; text-transform: uppercase; }
  .item { display: flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0; font-size: 0.85rem; }
  .item kbd { background: #f0f0f0; padding: 0.1rem 0.4rem; border: 1px solid #ddd; border-radius: 3px; font-family: inherit; font-size: 0.8rem; min-width: 1.5rem; text-align: center; }
  .close-btn { display: block; margin: 1rem auto 0; padding: 0.4rem 1.5rem; background: #4a90d9; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
</style>
