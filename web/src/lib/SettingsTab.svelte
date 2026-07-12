<script>
  import {
    getLocale,
    getNormaliseNodeIds,
    getStripPredicateDiacritics,
    setBoolSetting,
    setLocale,
  } from "./userConfig.svelte.js";

  let localeOptions = ["en", "fr", "de", "es", "it", "pt", "nl", "eo"];
  let selectedLocale = $state(getLocale());
  let normNodes = $state(getNormaliseNodeIds());
  let stripPred = $state(getStripPredicateDiacritics());
  let saving = $state(false);

  async function handleLocaleChange(e) {
    selectedLocale = e.target.value;
    saving = true;
    await setLocale(selectedLocale);
    saving = false;
  }

  async function toggleNormNodes() {
    normNodes = !normNodes;
    saving = true;
    await setBoolSetting("normalise_node_ids", normNodes);
    saving = false;
  }

  async function toggleStripPred() {
    stripPred = !stripPred;
    saving = true;
    await setBoolSetting("strip_diacritics_from_predicate_ids", stripPred);
    saving = false;
  }
</script>

<div class="settings-tab">
  <h2 class="settings-title">Settings</h2>

  <div class="setting-group">
    <h3 class="group-title">Locale</h3>
    <div class="setting-row">
      <label class="setting-label" for="locale-select">Interface language</label>
      <select
        id="locale-select"
        class="locale-select"
        value={selectedLocale}
        onchange={handleLocaleChange}
        disabled={saving}
      >
        {#each localeOptions as code}
          <option value={code}>{code.toUpperCase()}</option>
        {/each}
      </select>
    </div>
  </div>

  <div class="setting-group">
    <h3 class="group-title">ID Normalisation</h3>

    <div class="setting-row">
      <label class="setting-label" for="norm-nodes">
        Normalise node IDs
        <span class="setting-desc">Strip diacritics (â→a, é→e, etc.) from node IDs on creation</span>
      </label>
      <button
        id="norm-nodes"
        class="toggle"
        class:active={normNodes}
        onclick={toggleNormNodes}
        disabled={saving}
        role="switch"
        aria-checked={normNodes}
      >
        <span class="toggle-knob"></span>
      </button>
    </div>

    <div class="setting-row">
      <label class="setting-label" for="strip-pred">
        Strip predicate diacritics
        <span class="setting-desc">Strip diacritics from predicate IDs on creation</span>
      </label>
      <button
        id="strip-pred"
        class="toggle"
        class:active={stripPred}
        onclick={toggleStripPred}
        disabled={saving}
        role="switch"
        aria-checked={stripPred}
      >
        <span class="toggle-knob"></span>
      </button>
    </div>
  </div>

  {#if saving}
    <p class="saving-msg">Saving…</p>
  {/if}
</div>

<style>
  .settings-tab {
    padding: 1.25rem 1.5rem;
    max-width: 540px;
  }

  .settings-title {
    font-size: 1.1rem;
    color: #e0e0e0;
    font-weight: 600;
    margin: 0 0 1.25rem 0;
    font-family: monospace;
  }

  .setting-group {
    margin-bottom: 1.5rem;
  }

  .group-title {
    font-size: 0.85rem;
    color: #7c7c9a;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 0.75rem 0;
    font-family: monospace;
  }

  .setting-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.6rem 0;
    border-bottom: 1px solid #333;
  }

  .setting-label {
    font-size: 0.9rem;
    color: #e0e0e0;
    cursor: pointer;
    font-family: monospace;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }

  .setting-desc {
    font-size: 0.75rem;
    color: #7c7c9a;
    font-weight: 400;
  }

  .locale-select {
    background: #2a2a3e;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 0.4rem 0.6rem;
    color: #e0e0e0;
    font-size: 0.85rem;
    font-family: monospace;
    cursor: pointer;
    outline: none;
  }

  .locale-select:focus {
    border-color: #7c7c9a;
  }

  .locale-select:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .toggle {
    position: relative;
    width: 44px;
    height: 24px;
    background: #3a3a3a;
    border: 1px solid #555;
    border-radius: 12px;
    cursor: pointer;
    padding: 0;
    flex-shrink: 0;
    transition: background 0.15s, border-color 0.15s;
  }

  .toggle.active {
    background: #4a8a4a;
    border-color: #5a9a5a;
  }

  .toggle:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .toggle-knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 18px;
    height: 18px;
    background: #ccc;
    border-radius: 50%;
    transition: left 0.15s;
  }

  .toggle.active .toggle-knob {
    left: 22px;
    background: #fff;
  }

  .saving-msg {
    font-size: 0.8rem;
    color: #7c7c9a;
    font-family: monospace;
    margin-top: 0.5rem;
  }
</style>
