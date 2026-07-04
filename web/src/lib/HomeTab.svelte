<script>
  import { onMount } from "svelte";
  import { tabs, activeTabId, openTab } from "./tabStore.js";
  import { execute } from "./commandExecutor.js";

  let stats = $state(null);
  let chatInput = $state("");

  onMount(async () => {
    try {
      const res = await fetch("/api/v1/query/stats");
      stats = await res.json();
    } catch { stats = { nodes: 0, predicates: 0, triples: 0 }; }
  });

  async function handleChat(e) {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const msg = chatInput.trim();
    chatInput = "";

    // Check if it starts with ! — route to command
    if (msg.startsWith("!")) {
      const result = await execute(msg);
      if (result) openTab(result.type === "error" ? "error" : "status", "Result", result);
      return;
    }

    // LLM chat
    openTab("chat", "Chat", { type: "chat", data: { reply: "Thinking…" } });
    try {
      const res = await fetch("/api/v1/llm/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history: [] }),
      });
      const data = await res.json();
      openTab("chat", "Chat", { type: "chat", data }, { id: "chat", persistent: true });
    } catch (err) {
      openTab("error", "Error", { type: "error", message: String(err) });
    }
  }
</script>

<div class="home">
  <div class="hero">
    <h2>Semantika</h2>
    <p class="tagline">Your personal knowledge graph.</p>
  </div>

  {#if stats}
    <div class="stats-row">
      <div class="stat"><strong>{stats.nodes}</strong> nodes</div>
      <div class="stat"><strong>{stats.predicates}</strong> predicates</div>
      <div class="stat"><strong>{stats.triples}</strong> triples</div>
    </div>
  {/if}

  <form onsubmit={handleChat} class="chat-form">
    <textarea
      bind:value={chatInput}
      placeholder="Ask a question, type !command, or chat with LLM…"
      rows="2"
    ></textarea>
    <button type="submit" disabled={!chatInput.trim()}>Send</button>
  </form>

  <div class="quick-cmds">
    <h4>Quick commands</h4>
    <div class="cmd-grid">
      <button onclick={() => openTab("help", "Help", { type: "help" }, { id: "help", persistent: true })}>!help</button>
      <button onclick={async () => {
        const res = await fetch("/api/v1/command/execute", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({command:"stats"}) });
        openTab("status", "Stats", await res.json());
      }}>!stats</button>
      <button onclick={() => openTab("graph", "Graph", {}, { id: "graph", persistent: true })}>🌐 Graph</button>
    </div>
  </div>
</div>

<style>
  .home { padding: 1.5rem; max-width: 600px; margin: 0 auto; }
  .hero { text-align: center; margin-bottom: 1.5rem; }
  .hero h2 { margin: 0; font-size: 1.5rem; }
  .tagline { color: #888; margin: 0.3rem 0 0; }
  .stats-row {
    display: flex; justify-content: center; gap: 1.5rem;
    margin-bottom: 1.5rem;
  }
  .stat { text-align: center; font-size: 0.9rem; color: #666; }
  .stat strong { display: block; font-size: 1.3rem; color: #333; }
  .chat-form {
    display: flex; gap: 0.5rem; margin-bottom: 1.5rem;
  }
  .chat-form textarea {
    flex: 1; padding: 0.6rem; border: 1px solid #ccc; border-radius: 6px;
    font-family: inherit; font-size: 0.9rem; resize: none;
  }
  .chat-form button {
    padding: 0.6rem 1.2rem; background: #4a90d9; color: #fff;
    border: none; border-radius: 6px; cursor: pointer;
    font-size: 0.9rem; align-self: flex-end;
  }
  .chat-form button:disabled { opacity: 0.5; cursor: default; }
  .quick-cmds h4 { margin: 0 0 0.5rem; font-size: 0.9rem; color: #666; }
  .cmd-grid { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .cmd-grid button {
    padding: 0.4rem 0.8rem; border: 1px solid #ddd; background: #fff;
    border-radius: 4px; cursor: pointer; font-size: 0.85rem;
  }
  .cmd-grid button:hover { background: #f0f4ff; }
</style>
