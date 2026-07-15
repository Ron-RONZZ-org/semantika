<script>
  import { renderMarkdown } from "./markdown.js";
  import { execute } from "./commandExecutor.js";
  import { tabStore } from "./tabStore.svelte.js";

  let {
    messages = [],
    copiedIndex = -1,
    saveDialogIndex = -1,
    saveAlias = "",
    saveCommand = "",
    saveHint = "",
    onsave = () => {},
    oncopy = () => {},
    onsaveopen = () => {},
    onsavehide = () => {},
  } = $props();

  function stripHtml(html) {
    const div = document.createElement("div");
    div.innerHTML = html;
    return div.textContent || div.innerText || "";
  }

  function copyMessage(index) {
    const msg = messages[index];
    if (!msg) return;
    const text = msg.text || (msg.html ? stripHtml(msg.html) : "");
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      oncopy(index);
    }).catch(() => {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      oncopy(index);
    });
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
        onsave(alias, cmdTemplate);
      } else {
        const errMsg = result.data?.message || "Failed to save command";
        tabStore.open("error", "Error", { message: errMsg });
      }
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to save" });
    }
  }
</script>

{#if messages.length > 0}
  <div class="conversation">
    {#each messages as msg, i (i)}
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
                  <button class="btn-accept" onclick={() => {}}>Accept</button>
                  <button class="btn-reject" onclick={() => {}}>Reject</button>
                </div>
              </div>
            {/each}
          </div>
        {/if}
        {#if msg.role === "user" && msg.text && msg.text.trim().startsWith("!") && !msg.text.trim().startsWith("!user")}
          <div class="msg-actions">
            <button class="btn-save-cmd" onclick={() => onsaveopen(i, msg.text)}>Save Command</button>
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
                <button class="btn-cancel-save" onclick={onsavehide}>Cancel</button>
              </div>
            </div>
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
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
