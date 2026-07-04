<script>
  import { getCompletions } from "./commandTree.js";
  import { execute } from "./commandExecutor.js";

  let input = $state("");
  let suggestions = $state([]);
  let loading = $state(false);
  let { oncommand } = $props();

  function handleChange() {
    if (input.startsWith("!")) {
      suggestions = getCompletions(input);
    } else {
      suggestions = [];
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const cmd = input.trim();
    input = "";
    suggestions = [];
    loading = true;

    try {
      const result = await execute(cmd);
      oncommand?.(result);
    } catch (err) {
      oncommand?.({ type: "error", message: String(err) });
    } finally {
      loading = false;
    }
  }

  function selectSuggestion(text) {
    input = text + " ";
    suggestions = [];
  }
</script>

<form onsubmit={handleSubmit} class="command-bar">
  <div class="input-wrap">
    <span class="prompt">❯</span>
    <input
      type="text"
      bind:value={input}
      oninput={handleChange}
      placeholder="!node add, !search, !ask ..."
      autofocus
      disabled={loading}
    />
    {#if loading}
      <span class="spinner">⟳</span>
    {/if}
  </div>

  {#if suggestions.length > 0}
    <div class="suggestions">
      {#each suggestions as s}
        <button type="button" onclick={() => selectSuggestion(s.text)}>
          <code>{s.text}</code>
          <span class="desc">{s.desc}</span>
        </button>
      {/each}
    </div>
  {/if}
</form>

<style>
  .command-bar { position: relative; }
  .input-wrap {
    display: flex;
    align-items: center;
    background: #f0f0f0;
    border: 1px solid #ccc;
    border-radius: 6px;
    padding: 0.3rem 0.6rem;
  }
  .input-wrap:focus-within { border-color: #4a90d9; box-shadow: 0 0 0 2px rgba(74,144,217,0.15); }
  .prompt { color: #4a90d9; font-weight: bold; margin-right: 0.4rem; font-size: 0.9rem; }
  input {
    flex: 1;
    border: none;
    background: transparent;
    font-size: 0.95rem;
    outline: none;
    font-family: inherit;
  }
  .spinner { animation: spin 1s linear infinite; color: #888; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .suggestions {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 0 0 6px 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    z-index: 100;
    max-height: 200px;
    overflow-y: auto;
  }
  .suggestions button {
    display: flex;
    justify-content: space-between;
    width: 100%;
    padding: 0.4rem 0.8rem;
    text-align: left;
    border: none;
    background: none;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .suggestions button:hover { background: #f0f4ff; }
  .suggestions code { background: #e8eef8; padding: 0.1rem 0.3rem; border-radius: 3px; }
  .suggestions .desc { color: #888; font-size: 0.8rem; }
</style>
