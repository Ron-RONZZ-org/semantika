<script>
  import { popup } from "./popupStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";
  import { execute } from "./commandExecutor.js";
  import { renderMarkdown } from "./markdown.js";
  import ChatInput from "./ChatInput.svelte";
  import LlmSetupModal from "./LlmSetupModal.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import HomeHeader from "./HomeHeader.svelte";
  import MessageList from "./MessageList.svelte";
  import { parseCommand, parsePromptCommand } from "./parser.js";
  import { commandTree, findNode } from "./commandTree.js";
  import { shouldIntercept } from "./commandRouter.js";

  let hasSentLlmMessage = $state(false);
  let showLlmSetup = $state(false);
  let llmAvailable = $state(null);
  let pendingMessage = $state("");
  let messages = $state([]);
  let convoEl = $state(null);
  let isLoadingLlm = $state(false);

  /** @type {{
   *   name: string,
   *   expanded: string,
   *   raw: string,
   * } | null} */
  let expandedPrompt = $state(null);
  /** Index of the user message in `messages` that triggered the expand dialog. */
  let expandedPromptMsgIdx = $state(-1);

  /** @type {{
   *   tokens?: string[],
   *   flags?: Record<string,string>,
   *   session_id?: string,
   *   batch?: Array<{index:number, tokens:string[], flags:object, description:string}>,
   *   resumeUrl?: string,
   *   message: string
   * } | null} */
  let confirmRequest = $state(null);
  let rejectFeedback = $state("");
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

    // ── Prompt commands (/ prefix) ────────────────────────────────────
    // Step 1: Expand the template via /expand endpoint
    // Step 2: Show expanded text in a preview dialog
    // Step 3: On user confirm, send expanded text to LLM as a normal message
    if (trimmed.startsWith("/")) {
      // Prompt commands always need an LLM — show setup modal if not configured
      if (llmAvailable === null) {
        await checkLlmAvailable();
      }
      if (llmAvailable === false) {
        pendingMessage = trimmed;
        messages = messages.slice(0, -1);
        showLlmSetup = true;
        isLoadingLlm = false;
        return;
      }

      const parsed = parsePromptCommand(trimmed);
      if (!parsed || !parsed.name) {
        messages = messages.map((m, i) =>
          i === messages.length - 1
            ? { ...m, html: "<p>Usage: /command-name [args...]</p>", _streaming: false }
            : m,
        );
        isLoadingLlm = false;
        scrollToBottom();
        return;
      }

      // Call expand endpoint to preview the template
      try {
        const expandResp = await fetch("/api/v1/prompt-commands/expand", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: parsed.name, args: parsed.args }),
        });

        if (!expandResp.ok) {
          const detail = await expandResp.json().catch(() => ({}));
          const errMsg = detail.detail?.error || detail.detail || `HTTP ${expandResp.status}`;
          messages = messages.map((m, i) =>
            i === messages.length - 1
              ? { ...m, html: `<p>Error: ${errMsg}</p>`, _streaming: false }
              : m,
          );
          isLoadingLlm = false;
          scrollToBottom();
          return;
        }

        const expandData = await expandResp.json();
        expandedPrompt = {
          name: expandData.name,
          expanded: expandData.expanded,
          raw: trimmed,
        };
        // Track which user message this expand dialog relates to.
        // The original user message (index messages.length - 1) shows the
        // raw `/command` — we'll update it to the expanded text after sending.
        expandedPromptMsgIdx = messages.length - 1;
      } catch (err) {
        messages = messages.map((m, i) =>
          i === messages.length - 1
            ? { ...m, html: `<p>Error: ${err.message}</p>`, _streaming: false }
            : m,
        );
      }

      isLoadingLlm = false;
      scrollToBottom();
      return;
    }

    if (trimmed.startsWith("!")) {
      const routing = shouldIntercept(trimmed);
      if (routing.intercept) {
        try {
          const listInput = "!" + routing.listTokens.join(" ");
          const listResult = await execute(listInput);
          if (listResult.type === "error") {
            popup.show("error", "Error", listResult.data);
          } else {
            popup.showPersistent(listResult.type, listResult.title, listResult.data || {}, routing.listIdKey);
            popup.updateCache(listResult.data || {});
            tabStore.open("form", routing.addTitle || "Add", {
              form: routing.addFormType,
              initialData: routing.initialData || {},
            }, { idKey: `form-${routing.addFormType}` });
          }
        } catch (err) {
          popup.show("error", "Routing Error", { message: err.message || "Failed to open add form" });
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
              form, initialData: initialData || {},
            }, { idKey: `form-${form}` });
            scrollToBottom();
            return;
          }
        }

        if (result.type === "quiz") {
          tabStore.open("quiz", result.title || "Quiz", result.data, {});
          scrollToBottom();
          return;
        }

        if (result.type === "table") {
          popup.show("status", result.title || result.label || "Results", {
            type: "table", data: result.data, label: result.label || "",
          });
          scrollToBottom();
          return;
        }

        popup.show(result.type, result.title, result.data);
      } catch (err) {
        tabStore.open("error", "Error", {
          message: err.message || String(err), suggestion: err.suggestion || "",
        });
      }
      scrollToBottom();
      return;
    }

    if (llmAvailable === null) {
      await checkLlmAvailable();
    }
    if (llmAvailable === false) {
      pendingMessage = trimmed;
      messages = messages.slice(0, -1);
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

      if (data.type === "confirm") {
        // Legacy single-command confirmation
        confirmRequest = {
          tokens: data.tokens, flags: data.flags || {}, message: data.message || "Confirm command?",
        };
        rejectFeedback = "";
        messages = messages.map((m, i) =>
          i === msgIdx ? { ...m, html: `<p><em>Waiting for confirmation…</em></p>`, _streaming: false } : m,
        );
        isLoadingLlm = false;
        scrollToBottom();
        return;
      }

      if (data.type === "confirm_tool") {
        // Batch confirmation for write-level tools
        confirmRequest = {
          session_id: data.session_id,
          batch: data.batch || [],
          resumeUrl: "/api/v1/llm/chat/resume",
          message: data.message || "Confirm command?",
        };
        messages = messages.map((m, i) =>
          i === msgIdx ? { ...m, html: `<p><em>Waiting for confirmation…</em></p>`, _streaming: false } : m,
        );
        isLoadingLlm = false;
        scrollToBottom();
        return;
      }

      const reply = data.reply || data.data?.reply || (data.type === "chat" ? data.data?.html || "" : "");
      const html = renderMarkdown(reply);
      messages = messages.map((m, i) =>
        i === msgIdx ? { ...m, html, text: reply, _streaming: false, actions: [] } : m,
      );
    } catch (err) {
      messages = messages.map((m, i) =>
        i === msgIdx ? { ...m, html: `<p>Network error: ${err.message}</p>`, _streaming: false } : m,
      );
    }

    isLoadingLlm = false;
    scrollToBottom();
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (convoEl) convoEl.scrollTop = convoEl.scrollHeight;
    });
  }

  /** Update the user message at `expandedPromptMsgIdx` to show the final expanded text. */
  function _updateExpandedUserMsg(expandedText) {
    if (expandedPromptMsgIdx < 0 || expandedPromptMsgIdx >= messages.length) return;
    messages = messages.map((m, i) =>
      i === expandedPromptMsgIdx
        ? { ...m, text: expandedText, html: `<pre class="expanded-msg">${escapeHtml(expandedText)}</pre>` }
        : m,
    );
    expandedPromptMsgIdx = -1;
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /** Send the expanded prompt to the LLM as a normal chat message. */
  async function handleExpandConfirm(expandedText) {
    if (!expandedText || !expandedPrompt) return;
    const promptName = expandedPrompt.name;
    expandedPrompt = null;

    isLoadingLlm = true;
    const msgIdx = messages.length;
    messages = [...messages, { role: "assistant", html: "", text: "", actions: [], _streaming: true }];
    scrollToBottom();

    const context = buildContext();

    try {
      const resp = await fetch("/api/v1/llm/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: expandedText, context }),
      });

      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        const errMsg = detail.detail?.error || detail.detail || `HTTP ${resp.status}`;
        messages = messages.map((m, i) =>
          i === msgIdx
            ? { ...m, html: `<p>Error: ${errMsg}</p>`, text: errMsg, _streaming: false }
            : m,
        );
        _updateExpandedUserMsg(expandedText);
        isLoadingLlm = false;
        scrollToBottom();
        return;
      }

      const data = await resp.json();

      if (data.type === "confirm_tool") {
        confirmRequest = {
          session_id: data.session_id,
          batch: data.batch || [],
          resumeUrl: "/api/v1/llm/chat/resume",
          message: data.message || "Confirm command?",
        };
        messages = messages.map((m, i) =>
          i === msgIdx
            ? { ...m, html: `<p><em>Waiting for confirmation…</em></p>`, _streaming: false }
            : m,
        );
        _updateExpandedUserMsg(expandedText);
        isLoadingLlm = false;
        scrollToBottom();
        return;
      }

      const reply = data.reply || data.data?.reply || (data.type === "chat" ? data.data?.html || "" : "");
      const html = renderMarkdown(reply);
      messages = messages.map((m, i) =>
        i === msgIdx
          ? { ...m, html, text: reply, _streaming: false, actions: [] }
          : m,
      );
      _updateExpandedUserMsg(expandedText);
    } catch (err) {
      messages = messages.map((m, i) =>
        i === msgIdx
          ? { ...m, html: `<p>Network error: ${err.message}</p>`, _streaming: false }
          : m,
      );
      _updateExpandedUserMsg(expandedText);
    }

    isLoadingLlm = false;
    scrollToBottom();
  }

  function handleExpandDismiss() {
    expandedPrompt = null;
    expandedPromptMsgIdx = -1;
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
      } else { llmAvailable = false; }
    } catch { llmAvailable = false; }
  }

  /** Unified handler for per-item decisions + feedback from ConfirmDialog. */
  async function handleConfirmSubmit(decisions, feedback) {
    if (!confirmRequest) return;

    // ── Batch confirmation (LLM multi-tool) ────────────────────────────
    if (confirmRequest.session_id && confirmRequest.batch) {
      const { session_id, batch, resumeUrl } = confirmRequest;
      confirmRequest = null;
      rejectFeedback = "";

      // Remove "Waiting for confirmation" messages
      messages = messages.filter((m) => {
        const html = m.html || "";
        return !html.includes("Waiting for confirmation");
      });

      try {
        const resp = await fetch(resumeUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id,
            decisions,
            feedback,
          }),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => ({}));
          const errMsg = detail.detail?.error || detail.detail || `HTTP ${resp.status}`;
          popup.show("error", "Command Failed", { message: errMsg });
          return;
        }

        const data = await resp.json();

        // Handle nested confirm_tool (LLM issued more write commands)
        if (data.type === "confirm_tool") {
          confirmRequest = {
            session_id: data.session_id,
            batch: data.batch || [],
            resumeUrl,
            message: data.message || "Confirm command?",
          };
          return;
        }

        // Show result in conversation
        const replyHtml =
          data.data?.html ||
          (data.data?.message ? renderMarkdown(data.data.message) : "") ||
          (data.reply ? renderMarkdown(data.reply) : "") ||
          data.html ||
          "";
        const replyText = data.data?.message || data.reply || data.message || "";
        messages = [
          ...messages,
          { role: "assistant", html: replyHtml, text: replyText, _streaming: false, actions: [] },
        ];
        scrollToBottom();
      } catch (err) {
        popup.show("error", "Connection Error", { message: `Confirm failed: ${err.message}` });
      }
      return;
    }

    // ── Legacy single-command confirmation ────────────────────────────
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

  let _configuring = false;

  function handleLlmConfigured() {
    if (_configuring) return;
    _configuring = true;
    showLlmSetup = false;
    llmAvailable = true;
    const msg = pendingMessage;
    pendingMessage = "";
    if (msg) {
      setTimeout(() => { handleSubmit(msg); _configuring = false; }, 100);
    } else { _configuring = false; }
  }

  function handleLlmDismiss() {
    showLlmSetup = false;
    const msg = pendingMessage;
    pendingMessage = "";
    if (msg) {
      messages = [...messages, {
        role: "assistant",
        html: "<p>You can use <code>!commands</code> directly while the LLM is not configured. "
          + "Type <code>!help</code> to see available commands, or open the LLM setup again "
          + "from the settings later.</p>",
      }];
      hasSentLlmMessage = true;
    }
  }

  // MessageList callbacks
  function handleCopy(index) {
    copiedIndex = index;
    setTimeout(() => { if (copiedIndex === index) copiedIndex = -1; }, 1500);
  }

  function handleSaveOpen(index, text) {
    const cmdText = text.replace(/^!/, "").trim();
    saveCommand = cmdText;
    saveAlias = "";
    saveHint = "";
    saveDialogIndex = index;
  }

  function handleSaveDone(alias, cmdTemplate) {
    saveDialogIndex = -1;
    messages = [...messages, {
      role: "assistant",
      html: `<p><em>Saved command <strong>!${alias}</strong> → <code>${cmdTemplate}</code></em></p>`,
    }];
  }

  function handleSaveHide() {
    saveDialogIndex = -1;
  }
</script>

<div class="home-tab">
  <HomeHeader {stats} compact={hasSentLlmMessage} />

  <div class="conversation-wrap" bind:this={convoEl}>
    <MessageList
      {messages}
      {copiedIndex}
      {saveDialogIndex}
      bind:saveAlias
      bind:saveCommand
      bind:saveHint
      oncopy={handleCopy}
      onsaveopen={handleSaveOpen}
      onsave={handleSaveDone}
      onsavehide={handleSaveHide}
    />
  </div>

  <div class="input-container" class:at-bottom={hasSentLlmMessage}>
    <ChatInput centered={!hasSentLlmMessage} onSubmit={handleSubmit} />
  </div>
</div>

{#if showLlmSetup}
  <LlmSetupModal onConfigured={handleLlmConfigured} onDismiss={handleLlmDismiss} />
{/if}

{#if expandedPrompt}
  <!-- Expanded prompt preview dialog -->
  <div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label="Expanded Prompt"
       onclick={handleExpandDismiss} onkeydown={() => {}} tabindex="0">
    <div class="expand-box" onclick={(e) => e.stopPropagation()}>
      <h3 class="expand-heading">Expanded Prompt: /{expandedPrompt.name}</h3>
      <div class="expand-preview">{expandedPrompt.expanded}</div>
      <p class="expand-hint">This is the expanded prompt that will be sent to the LLM.</p>
      <div class="actions">
        <button class="btn btn-primary" onclick={() => handleExpandConfirm(expandedPrompt.expanded)}>
          Send to LLM
        </button>
        <button class="btn" onclick={handleExpandDismiss}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

{#if confirmRequest}
  <ConfirmDialog
    message={confirmRequest.message}
    batch={confirmRequest.batch || []}
    onSubmit={handleConfirmSubmit}
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
  .conversation-wrap {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
  }
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

  /* ── Expanded prompt preview dialog ────────── */
  .confirm-overlay {
    position: absolute; inset: 0; background: rgba(0,0,0,0.6);
    display: flex; align-items: center; justify-content: center; z-index: 100;
  }
  .expand-box {
    background: #1e1e32; border: 1px solid #444; border-radius: 8px;
    padding: 1.5rem 2rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    max-width: 680px;
    width: 90%;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
  }
  .expand-heading {
    margin: 0 0 0.75rem 0;
    color: #c0c0e0;
    font-size: 1rem;
  }
  .expand-preview {
    background: #16162a;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 0.75rem 1rem;
    color: #d0d0e0;
    font-size: 0.88rem;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-y: auto;
    max-height: 55vh;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  .expand-hint {
    color: #888;
    font-size: 0.8rem;
    margin: 0.5rem 0 0.75rem 0;
  }
  .actions {
    display: flex;
    gap: 0.75rem;
    justify-content: center;
    flex-wrap: wrap;
  }
  .btn {
    padding: 0.4rem 1rem; border: 1px solid #555; border-radius: 4px;
    background: #2a2a3e; color: #e0e0e0; cursor: pointer; font-size: 0.85rem;
  }
  .btn:hover { background: #3a3a5a; }
  .btn-primary {
    background: #2a4a5a; color: #e0e0e0; border-color: #3a6a7a;
  }
  .btn-primary:hover { background: #3a5a6a; }

  /* ── Expanded message in conversation history ── */
  :global(.expanded-msg) {
    background: #16162a;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 0.6rem 0.8rem;
    font-size: 0.85rem;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-x: auto;
    color: #c8c8e0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0.25rem 0;
  }
</style>
