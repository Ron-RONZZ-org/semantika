<script>
  import { popup } from "./popupStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";
  import { execute } from "./commandExecutor.js";
  import { renderMarkdown } from "./markdown.js";
  import ChatInput from "./ChatInput.svelte";
  import LlmSetupModal from "./LlmSetupModal.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import { parseCommand } from "./parser.js";
  import { commandTree, findNode } from "./commandTree.js";
  import { shouldIntercept } from "./commandRouter.js";

  let hasSentLlmMessage = $state(false);
  let showLlmSetup = $state(false);
  let llmAvailable = $state(null);
  let messages = $state([]);
  let convoEl = $state(null);
  let isLoadingLlm = $state(false);

  /** @type {{ tokens: string[], flags: Record<string,string>, message: string } | null} */
  let confirmRequest = $state(null);
  let saveDialogIndex = $state(-1);
  let saveAlias = $state("");
  let saveCommand = $state("");
  let saveHint = $state("");
  let copiedIndex = $state(-1);

  let stats = $state(null);

  async function fetchStats() {
    try {
      const res = await fetch("/api/v1/query/stats");
      stats = await res.json();
    } catch { stats = { nodes: 0, predicates: 0, triples: 0 }; }
  }
  fetchStats();

  function buildContext() {
    const ctx = [];
    for (const msg of messages.slice(-20)) {
      if (msg.role === "user" && msg.text) {
        ctx.push({ role: "user", content: msg.text });
      } else if (msg.role === "assistant" && (msg.text || msg.html)) {
        const plain = msg.text || (msg.html ? stripHtml(msg.html) : "");
        if (plain) {
          ctx.push({ role: "assistant", content: plain });
        }
      }
    }
    return ctx;
  }

  function stripHtml(html) {
    const div = document.createElement("div");
    div.innerHTML = html;
    return div.textContent || div.innerText || "";
  }

  async function handleSubmit(input) {
    const trimmed = input.trim();
    if (!trimmed || isLoadingLlm) return;

    messages = [...messages, { role: "user", text: trimmed }];
    hasSentLlmMessage = true;

    if (trimmed.startsWith("!")) {
      const routing = shouldIntercept(trimmed);
      if (routing.intercept) {
        try {
          const listInput = "!" + routing.listTokens.join(" ");
          const listResult = await execute(listInput);
          if (listResult.type === "error") {
            popup.show("error", "Error", listResult.data);
          } else {
            popup.showPersistent(
              listResult.type,
              listResult.title,
              listResult.data || {},
              routing.listIdKey,
            );
            popup.updateCache(listResult.data || {});
            tabStore.open("form", routing.addTitle || "Add", {
              form: routing.addFormType,
              initialData: routing.initialData || {},
            }, { idKey: `form-${routing.addFormType}` });
          }
        } catch (err) {
          popup.show("error", "Routing Error", {
            message: err.message || "Failed to open add form",
          });
        }
        scrollToBottom();
        return;
      }

      try {
        const result = await execute(trimmed);

        if (result.type === "form-required") {
          const { form, initialData } = result.data || {};
          if (form) {
            tabStore.open("form", result.title || "Complete Form", {
              form,
              initialData: initialData || {},
            }, { idKey: `form-${form}` });
            scrollToBottom();
            return;
          }
        }

        // Quiz mode: open interactive quiz panel
        if (result.type === "quiz") {
          tabStore.open("quiz", result.title || "Quiz", result.data, {});
          scrollToBottom();
          return;
        }

        // Transform "table" results into a format StatusPopup can render
        if (result.type === "table") {
          popup.show("status", result.title || result.label || "Results", {
            type: "table",
            data: result.data,
            label: result.label || "",
          });
          scrollToBottom();
          return;
        }

        popup.show(result.type, result.title, result.data);
      } catch (err) {
        tabStore.open("error", "Error", {
          message: err.message || String(err),
          suggestion: err.suggestion || "",
        });
      }
      scrollToBottom();
      return;
    }

    if (llmAvailable === null) {
      await checkLlmAvailable();
    }
    if (llmAvailable === false) {
      showLlmSetup = true;
      isLoadingLlm = false;
      return;
    }

    isLoadingLlm = true;
    const msgIdx = messages.length;
    messages = [...messages, { role: "assistant", html: "", text: "", actions: [], _streaming: true }];
    scrollToBottom();

    const context = buildContext();

    try {
      const resp = await fetch("/api/v1/llm/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: trimmed, context }),
      });

      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        const errMsg = detail.detail?.error || detail.detail || `HTTP ${resp.status}`;
        messages = messages.map((m, i) =>
          i === msgIdx ? { ...m, html: `<p>Error: ${errMsg}</p>`, _streaming: false } : m,
        );
        isLoadingLlm = false;
        scrollToBottom();
        return;
      }

      const data = await resp.json();

      // Handle permission-gated destructive commands
      if (data.type === "confirm") {
        confirmRequest = {
          tokens: data.tokens,
          flags: data.flags || {},
          message: data.message || "Confirm destructive command?",
        };
        messages = messages.map((m, i) =>
          i === msgIdx ? { ...m, html: `<p><em>Waiting for confirmation…</em></p>`, _streaming: false } : m,
        );
        isLoadingLlm = false;
        scrollToBottom();
        return;
      }

      const reply = data.reply || data.data?.reply || JSON.stringify(data);
      const html = renderMarkdown(reply);
      messages = messages.map((m, i) =>
        i === msgIdx ? { ...m, html, text: reply, _streaming: false, actions: [] } : m,
      );
    } catch (err) {
      messages = messages.map((m, i) =>
        i === msgIdx
          ? { ...m, html: `<p>Network error: ${err.message}</p>`, _streaming: false }
          : m,
      );
    }

    isLoadingLlm = false;
    scrollToBottom();
  }

  function copyMessage(index) {
    const msg = messages[index];
    if (!msg) return;
    const text = msg.text || (msg.html ? stripHtml(msg.html) : "");
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      copiedIndex = index;
      setTimeout(() => { if (copiedIndex === index) copiedIndex = -1; }, 1500);
    }).catch(() => {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      copiedIndex = index;
      setTimeout(() => { if (copiedIndex === index) copiedIndex = -1; }, 1500);
    });
  }

  function openSaveDialog(index, text) {
    const cmdText = text.replace(/^!/, "").trim();
    saveCommand = cmdText;
    saveAlias = "";
    saveHint = "";
    saveDialogIndex = index;
  }

  async function handleSaveCommand() {
    if (!saveAlias.trim() || !saveCommand.trim()) return;
    const alias = saveAlias.trim();
    const cmdTemplate = saveCommand.trim();
    const hint = saveHint.trim();
    try {
      const result = await execute(
        `!user saved-commands add --alias ${alias} --command "${cmdTemplate}"${hint ? ` --hint "${hint}"` : ""}`
      );
      if (result.type === "status") {
        saveDialogIndex = -1;
        messages = [...messages, {
          role: "assistant",
          html: `<p><em>Saved command <strong>!${alias}</strong> → <code>${cmdTemplate}</code></em></p>`,
        }];
      } else {
        const errMsg = result.data?.message || "Failed to save command";
        tabStore.open("error", "Error", { message: errMsg });
      }
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to save" });
    }
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (convoEl) convoEl.scrollTop = convoEl.scrollHeight;
    });
  }

  $effect(() => {
    refreshDataCache();
  });

  async function refreshDataCache() {
    try {
      const [nodesRes, predsRes] = await Promise.all([
        fetch("/api/v1/graph/nodes?limit=100").catch(() => null),
        fetch("/api/v1/graph/predicates?limit=100").catch(() => null),
      ]);
      const nodes = nodesRes ? (await nodesRes.json()).nodes || [] : [];
      const predicates = predsRes ? (await predsRes.json()).predicates || [] : [];
      popup.updateCache({ nodes, predicates });
    } catch { /* ignore */ }
  }

  async function checkLlmAvailable() {
    try {
      const resp = await fetch("/api/v1/llm/config");
      if (resp.ok) {
        const cfg = await resp.json();
        llmAvailable = !!cfg.available;
      } else {
        llmAvailable = false;
      }
    } catch {
      llmAvailable = false;
    }
  }

  async function handleConfirmCommand() {
    if (!confirmRequest) return;
    const { tokens, flags } = confirmRequest;
    confirmRequest = null;
    try {
      const resp = await fetch("/api/v1/llm/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens, flags }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        const errMsg = data.detail?.error || data.detail || `HTTP ${resp.status}`;
        popup.show("error", "Command Failed", { message: errMsg });
        return;
      }
      popup.show(data.type || "status", data.title || "Done", data.data || {});
    } catch (err) {
      popup.show("error", "Connection Error", { message: `Confirm failed: ${err.message}` });
    }
  }

  function handleLlmConfigured() {
    showLlmSetup = false;
    llmAvailable = true;
  }
</script>

<div class="home-tab">
  <div class="brand" class:compact={hasSentLlmMessage}>
    <h1 class="logo">semantika</h1>
    {#if !hasSentLlmMessage}
      <p class="tagline">Command-driven knowledge graph</p>
    {/if}
  </div>

  {#if !hasSentLlmMessage && stats}
    <div class="stats-row">
      <div class="stat"><strong>{stats.nodes}</strong> nodes</div>
      <div class="stat"><strong>{stats.predicates}</strong> predicates</div>
      <div class="stat"><strong>{stats.triples}</strong> triples</div>
    </div>
  {/if}

  {#if messages.length > 0}
    <div class="conversation" bind:this={convoEl}>
      {#each messages as msg, i}
        <div class="message" class:user={msg.role === "user"} class:assistant={msg.role === "assistant"}>
          <div class="msg-header">
            <span class="msg-role">{msg.role === "user" ? "You" : "Semantika"}</span>
            <button
              class="btn-copy"
              title="Copy message"
              onclick={() => copyMessage(i)}
            >
              {#if copiedIndex === i}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              {:else}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              {/if}
            </button>
          </div>
          {#if msg.html}
            <div class="msg-body">{@html msg.html}</div>
          {:else if msg.text}
            <div class="msg-body">{msg.text}</div>
          {:else if msg._streaming}
            <div class="msg-body"><em>Thinking…</em></div>
          {/if}
          {#if msg.actions && msg.actions.length > 0}
            <div class="actions">
              {#each msg.actions as action}
                <div class="action-card">
                  <p class="action-label">{action.label || action.action}</p>
                  <div class="action-buttons">
                    <button class="btn-accept" onclick={() => handleActionAccept(action)}>Accept</button>
                    <button class="btn-reject" onclick={() => handleActionReject(action)}>Reject</button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
          {#if msg.role === "user" && msg.text && msg.text.trim().startsWith("!") && !msg.text.trim().startsWith("!user")}
            <div class="msg-actions">
              <button class="btn-save-cmd" onclick={() => openSaveDialog(i, msg.text)}>Save Command</button>
            </div>
          {/if}
          {#if i === saveDialogIndex}
            <div class="save-dialog">
              <div class="save-dialog-inner">
                <div class="save-row">
                  <label>
                    <span class="save-label">Alias</span>
                    <input type="text" bind:value={saveAlias} placeholder="e.g. my-cmd" />
                  </label>
                </div>
                <div class="save-row">
                  <label>
                    <span class="save-label">Command <em>(without !)</em></span>
                    <input type="text" bind:value={saveCommand} placeholder="node list" />
                  </label>
                </div>
                <div class="save-row">
                  <label>
                    <span class="save-label">Hint</span>
                    <input type="text" bind:value={saveHint} placeholder="Short description" />
                  </label>
                </div>
                <div class="save-actions">
                  <button class="btn-save" onclick={handleSaveCommand}>Save</button>
                  <button class="btn-cancel-save" onclick={() => { saveDialogIndex = -1; }}>Cancel</button>
                </div>
              </div>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  <div class="input-container" class:at-bottom={hasSentLlmMessage}>
    <ChatInput centered={!hasSentLlmMessage} onSubmit={handleSubmit} />
  </div>
</div>

{#if showLlmSetup}
  <LlmSetupModal
    onConfigured={handleLlmConfigured}
    onDismiss={() => { showLlmSetup = false; }}
  />
{/if}

{#if confirmRequest}
  <ConfirmDialog
    message={confirmRequest.message}
    onConfirm={handleConfirmCommand}
    onDismiss={() => { confirmRequest = null; }}
  />
{/if}

<style>
  .home-tab {
    display: flex;
    flex-direction: column;
    height: 100%;
    position: relative;
  }
  .brand {
    text-align: center;
    padding: 3rem 1rem 1rem;
    transition: all 0.4s ease;
    flex-shrink: 0;
  }
  .brand.compact {
    padding: 0.75rem 1rem 0.25rem;
  }
  .logo {
    font-size: 1.6rem;
    font-weight: 300;
    color: #7c7c9a;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-family: monospace;
  }
  .brand.compact .logo {
    font-size: 0.9rem;
    opacity: 0.6;
  }
  .tagline {
    font-size: 0.8rem;
    color: #5a5a7a;
    font-family: monospace;
    margin-top: 0.4rem;
  }
  .stats-row {
    display: flex;
    justify-content: center;
    gap: 1.5rem;
    padding-bottom: 1rem;
    flex-shrink: 0;
  }
  .stat {
    text-align: center;
    font-family: monospace;
    font-size: 0.78rem;
    color: #5a5a7a;
  }
  .stat strong {
    display: block;
    font-size: 1.1rem;
    color: #7c7c9a;
  }
  .conversation {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    min-height: 0;
  }
  .message {
    max-width: 85%;
    padding: 0.6rem 0.9rem;
    border-radius: 10px;
    font-family: monospace;
    font-size: 0.88rem;
    line-height: 1.5;
    animation: fadeIn 0.2s ease;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .message.user {
    align-self: flex-end;
    background: #2a2a44;
    border: 1px solid #3a3a5a;
    color: #e0e0e0;
  }
  .message.assistant {
    align-self: flex-start;
    background: #1a1a30;
    border: 1px solid #333;
    color: #d0d0e0;
  }
  .msg-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.3rem;
  }
  .btn-copy {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: #5a5a7a;
    cursor: pointer;
    padding: 2px;
    border-radius: 4px;
    opacity: 0;
    transition: opacity 0.15s, color 0.15s, background 0.15s;
  }
  .message:hover .btn-copy {
    opacity: 1;
  }
  .btn-copy:hover {
    color: #b0b0c0;
    background: #3a3a5a;
  }
  .msg-role {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #7c7c9a;
  }
  .msg-body { white-space: pre-wrap; word-break: break-word; }
  .msg-body :global(p) { margin: 0.3rem 0; }
  .msg-body :global(pre) {
    background: #111; padding: 0.5rem; border-radius: 6px;
    overflow-x: auto; font-size: 0.8rem; margin: 0.4rem 0;
  }
  .msg-body :global(code) {
    background: #111; padding: 1px 4px; border-radius: 3px; font-size: 0.82rem;
  }
  .msg-body :global(pre code) { background: none; padding: 0; }
  .msg-body :global(a) { color: #8a8acc; text-decoration: underline; }
  .msg-body :global(blockquote) {
    border-left: 2px solid #5a5a7a; padding-left: 0.6rem;
    margin: 0.4rem 0; color: #9a9ab0;
  }
  .msg-body :global(ul), .msg-body :global(ol) { padding-left: 1.2rem; margin: 0.3rem 0; }
  .msg-body :global(li) { margin: 0.1rem 0; }
  .msg-body :global(h1), .msg-body :global(h2), .msg-body :global(h3) {
    margin: 0.5rem 0 0.2rem; color: #e0e0e0;
  }
  .msg-body :global(hr) { border: none; border-top: 1px solid #333; margin: 0.5rem 0; }
  .actions { margin-top: 0.5rem; }
  .action-card {
    background: #1e1e32; border: 1px solid #4a4a6a;
    border-radius: 8px; padding: 0.6rem; margin-top: 0.4rem;
  }
  .action-label { font-size: 0.8rem; color: #b0b0c0; margin-bottom: 0.4rem; }
  .action-buttons { display: flex; gap: 0.4rem; }
  .btn-accept, .btn-reject {
    padding: 0.25rem 0.8rem; border-radius: 6px; border: 1px solid #444;
    font-family: monospace; font-size: 0.78rem; cursor: pointer; transition: background 0.1s;
  }
  .btn-accept { background: #1a3a1a; color: #6aaa6a; border-color: #3a6a3a; }
  .btn-accept:hover { background: #2a4a2a; }
  .btn-reject { background: #3a1a1a; color: #aa6a6a; border-color: #6a3a3a; }
  .btn-reject:hover { background: #4a2a2a; }
  .input-container {
    padding: 0.75rem 1rem;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    transition: all 0.4s ease;
  }
  .input-container.at-bottom {
    border-top: 1px solid #333;
    background: #1a1a2e;
  }
  .msg-actions { margin-top: 0.35rem; display: flex; gap: 0.3rem; }
  .btn-save-cmd {
    background: transparent; border: 1px solid #4a4a6a; border-radius: 4px;
    padding: 0.15rem 0.5rem; font-family: monospace; font-size: 0.72rem;
    color: #7c7c9a; cursor: pointer; transition: all 0.1s;
  }
  .btn-save-cmd:hover { background: #2a2a44; color: #b0b0c0; border-color: #6a6a8a; }
  .save-dialog {
    margin-top: 0.4rem; padding: 0.5rem; background: #1e1e32;
    border: 1px solid #4a4a6a; border-radius: 8px;
  }
  .save-dialog-inner { display: flex; flex-direction: column; gap: 0.3rem; }
  .save-row label {
    display: flex; flex-direction: column; gap: 0.15rem;
  }
  .save-label { font-size: 0.72rem; color: #7c7c9a; }
  .save-label em { font-style: normal; color: #5a5a7a; }
  .save-row input {
    background: #16162a; border: 1px solid #333; border-radius: 4px;
    padding: 0.25rem 0.4rem; color: #e0e0e0; font-family: monospace; font-size: 0.82rem; outline: none;
  }
  .save-row input:focus { border-color: #5a5a8a; }
  .save-actions { display: flex; gap: 0.3rem; margin-top: 0.3rem; }
  .btn-save {
    background: #2a4a2a; color: #6aaa6a; border: 1px solid #3a6a3a;
    border-radius: 4px; padding: 0.2rem 0.6rem; font-family: monospace; font-size: 0.78rem; cursor: pointer;
  }
  .btn-save:hover { background: #3a5a3a; }
  .btn-cancel-save {
    background: transparent; color: #7c7c9a; border: 1px solid #444;
    border-radius: 4px; padding: 0.2rem 0.6rem; font-family: monospace; font-size: 0.78rem; cursor: pointer;
  }
  .btn-cancel-save:hover { background: #2a2a3e; }
</style>
