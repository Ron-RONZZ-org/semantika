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
  import { parseCommand } from "./parser.js";
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

    // ── Prompt commands (/ prefix) → show in conversation, not popup ───
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

      isLoadingLlm = true;
      const msgIdx = messages.length;
      messages = [...messages, { role: "assistant", html: "", text: "", actions: [], _streaming: true }];
      scrollToBottom();

      try {
        const result = await execute(trimmed);

        if (result.type === "error") {
          const errMsg = result.data?.message || "Command failed";
          messages = messages.map((m, i) =>
            i === msgIdx
              ? { ...m, html: `<p>${errMsg}</p>`, text: errMsg, _streaming: false }
              : m,
          );
        } else if (result.type === "confirm_tool") {
          // Batch confirmation for write-level tools
          confirmRequest = {
            session_id: result.session_id,
            batch: result.batch || [],
            resumeUrl: "/api/v1/prompt-commands/execute/resume",
            message: result.message || "Confirm command?",
          };
          messages = messages.map((m, i) =>
            i === msgIdx
              ? { ...m, html: `<p><em>Waiting for confirmation…</em></p>`, _streaming: false }
              : m,
          );
        } else {
          const replyHtml =
            result.data?.html ||
            (result.data?.message ? renderMarkdown(result.data.message) : "") ||
            (result.data?.reply ? renderMarkdown(result.data.reply) : "") ||
            (result.html ? renderMarkdown(result.html) : "") ||
            (result.message ? renderMarkdown(result.message) : "");
          const replyText = result.data?.message || result.data?.reply || result.message || "";
          messages = messages.map((m, i) =>
            i === msgIdx
              ? { ...m, html: replyHtml, text: replyText, _streaming: false }
              : m,
          );
        }
      } catch (err) {
        messages = messages.map((m, i) =>
          i === msgIdx
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

  async function handleConfirmCommand() {
    if (!confirmRequest) return;

    // ── Batch confirmation (LLM multi-tool) ────────────────────────────
    if (confirmRequest.session_id && confirmRequest.batch) {
      const { session_id, batch, resumeUrl } = confirmRequest;
      confirmRequest = null;

      try {
        const resp = await fetch(resumeUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id,
            decisions: Object.fromEntries(batch.map((b) => [b.index, true])),
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

        // Show result in conversation: remove "Waiting for confirmation" message
        // and append the final answer as a new assistant message.
        messages = messages.filter((m) => {
          const html = m.html || "";
          return !html.includes("Waiting for confirmation");
        });

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

  async function handleRejectFeedback(feedback) {
    if (!confirmRequest) return;

    // ── Batch rejection: call resume with confirmed=false ──────────────
    if (confirmRequest.session_id && confirmRequest.batch) {
      const { session_id, batch, resumeUrl } = confirmRequest;
      confirmRequest = null;
      rejectFeedback = "";
      messages = messages.filter((m) => {
        const html = m.html || "";
        return !html.includes("Waiting for confirmation");
      });

      // Call resume with confirmed=false so the LLM sees the rejection and
      // can suggest an alternative in the same tool loop.
      try {
        const resp = await fetch(resumeUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id,
            decisions: Object.fromEntries(batch.map((b) => [b.index, false])),
          }),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => ({}));
          const errMsg = detail.detail?.error || detail.detail || `HTTP ${resp.status}`;
          popup.show("error", "Command Failed", { message: errMsg });
          return;
        }

        const data = await resp.json();

        // Handle nested confirm_tool
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
        popup.show("error", "Connection Error", { message: `Reject failed: ${err.message}` });
      }
      return;
    }

    // ── Legacy single-command rejection ────────────────────────────────
    const { tokens } = confirmRequest;
    confirmRequest = null;
    rejectFeedback = "";
    messages = messages.filter((m) => {
      const html = m.html || "";
      return !html.includes("Waiting for confirmation");
    });

    const contextMsg = `The LLM suggested running \`!${tokens.join(" ")}\` but the user rejected it with this feedback: "${feedback}". Please suggest an alternative approach.`;
    messages = [...messages, { role: "user", text: contextMsg }];
    hasSentLlmMessage = true;

    const cleanContext = buildContext();
    isLoadingLlm = true;
    const msgIdx = messages.length;
    messages = [...messages, { role: "assistant", html: "", text: "", actions: [], _streaming: true }];
    scrollToBottom();

    try {
      const resp = await fetch("/api/v1/llm/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: contextMsg, context: cleanContext }),
      });
      const data = await resp.ok ? await resp.json() : { reply: "Sorry, something went wrong." };
      const reply = data.reply || data.data?.reply || "";
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

{#if confirmRequest}
  <ConfirmDialog
    message={confirmRequest.message}
    batch={confirmRequest.batch || []}
    onConfirm={handleConfirmCommand}
    onDismiss={() => { confirmRequest = null; }}
    onFeedback={handleRejectFeedback}
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
</style>
