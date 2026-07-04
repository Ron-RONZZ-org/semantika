<script>
  let input = $state("");
  let suggestions = $state([]);

  let { oncommand } = $props();

  async function handleSubmit(e) {
    e.preventDefault();
    if (!input.trim()) return;

    const cmd = input.trim();
    input = "";
    suggestions = [];

    try {
      const res = await fetch("/api/v1/command/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      });
      const result = await res.json();
      oncommand?.(result);
    } catch (err) {
      oncommand?.({ type: "error", message: String(err) });
    }
  }

  let debounceTimer;
  async function handleInput() {
    clearTimeout(debounceTimer);
    const val = input.trim();
    if (!val.startsWith("!") || val.length < 2) {
      suggestions = [];
      return;
    }
    debounceTimer = setTimeout(async () => {
      try {
        const res = await fetch("/api/v1/command/help");
        const data = await res.json();
        const cmds = data.commands || [];
        suggestions = cmds
          .filter(c => c.cmd.includes(val.toLowerCase()))
          .slice(0, 5);
      } catch { suggestions = []; }
    }, 200);
  }
</script>

<form onsubmit={handleSubmit} class="command-bar">
  <input
    type="text"
    bind:value={input}
    oninput={handleInput}
    placeholder='Type !command or ask naturally…'
    autofocus
  />
  {#if suggestions.length > 0}
    <div class="suggestions">
      {#each suggestions as s}
        <button type="button" onclick={() => { input = s.cmd; suggestions = []; }}>
          <code>{s.cmd}</code> — {s.desc}
        </button>
      {/each}
    </div>
  {/if}
</form>

<style>
  .command-bar {
    position: relative;
  }
  .command-bar input {
    width: 100%;
    padding: 0.6rem 1rem;
    font-size: 1rem;
    border: 1px solid #ccc;
    border-radius: 6px;
    box-sizing: border-box;
  }
  .command-bar input:focus {
    outline: none;
    border-color: #4a90d9;
    box-shadow: 0 0 0 2px rgba(74, 144, 217, 0.2);
  }
  .suggestions {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 0 0 6px 6px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    z-index: 100;
    max-height: 200px;
    overflow-y: auto;
  }
  .suggestions button {
    display: block;
    width: 100%;
    padding: 0.5rem 1rem;
    text-align: left;
    border: none;
    background: none;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .suggestions button:hover { background: #f0f0f0; }
  .suggestions code { background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 3px; }
</style>
