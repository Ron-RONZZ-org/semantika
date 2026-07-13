<script>
  import PopupOverlay from "./lib/PopupOverlay.svelte";
  import BannerContainer from "./lib/BannerContainer.svelte";
  import ConfirmDialog from "./lib/ConfirmDialog.svelte";
  import { popup } from "./lib/popupStore.svelte.js";
  import { tabStore } from "./lib/tabStore.svelte.js";
  import { dirtyFormStore } from "./lib/dirtyFormStore.svelte.js";
  import { execute } from "./lib/commandExecutor.js";
  import { shouldIntercept } from "./lib/commandRouter.js";
  import { findNode } from "./lib/commandTree.js";
  import { parseCommand } from "./lib/parser.js";
  import { initLocale } from "./lib/userConfig.svelte.js";

  /** @type {{ tokens: string[], flags: Record<string,string>, message: string } | null} */
  let confirmRequest = $state(null);

  let isLoading = $state(false);

  $effect(() => { initLocale(); });

  function loadingLabel(input) {
    const t = input.trim();
    if (t.startsWith("/")) {
      const parts = t.slice(1).trimStart().split(/\s+/);
      const cmd = parts[0] || "";
      return cmd ? `/${cmd}\u2026` : "Prompt command\u2026";
    }
    if (!t.startsWith("!")) return "Thinking\u2026";
    const parts = t.slice(1).split(/\s+/);
    const cmd = parts.slice(0, 2).join(" ");
    if (!cmd) return "Working\u2026";
    return `${cmd}\u2026`;
  }

  async function handleCommand(input) {
    const trimmed = input.trim();
    if (!trimmed) return;

    isLoading = true;

    try {
      if (trimmed.startsWith("!")) {
        const routing = shouldIntercept(trimmed);
        if (routing.intercept) {
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
            const enrichedInitial = {
              ...(routing.initialData || {}),
              _returnIdKey: routing.listIdKey ? `persistent-${routing.listIdKey}` : undefined,
            };
            tabStore.open("form", routing.addTitle || "Add", {
              form: routing.addFormType,
              initialData: enrichedInitial,
            }, { idKey: `form-${routing.addFormType}` });
          }
          isLoading = false;
          return;
        }
      }

      popup.showLoading(loadingLabel(input));

      const result = await execute(input);

      if (result.type === "confirm") {
        // Show confirmation dialog for LLM-generated destructive commands
        confirmRequest = {
          tokens: result.tokens,
          flags: result.flags || {},
          message: result.message || "Confirm destructive command?",
        };
        return;
      }

      if (result.type === "form-required") {
        const { form, initialData } = result.data || {};
        if (form === "sparql-editor") {
          tabStore.open("sparql-editor", "SPARQL Query", {}, { idKey: "sparql-editor" });
          isLoading = false;
          return;
        }
        if (form) {
          const activeId = tabStore.active?.id;
          if (activeId) tabStore.close(activeId);
          tabStore.open("form", result.title || "Complete Form", {
            form,
            initialData: initialData || {},
          }, { idKey: `form-${form}` });
          isLoading = false;
          return;
        }
      }

      // Transform "table" results into a format StatusPopup can render
      if (result.type === "table") {
        popup.show("status", result.title || result.label || "Results", {
          type: "table",
          data: result.data,
          label: result.label || "",
        });
        isLoading = false;
        return;
      }

      popup.show(result.type, result.title, result.data);
    } catch (err) {
      popup.show("error", "Error", {
        message: err.message || String(err),
        suggestion: err.suggestion || "",
      });
    } finally {
      isLoading = false;
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


</script>

<svelte:window onbeforeunload={(e) => {
    if (dirtyFormStore.hasAnyDirty) {
      e.preventDefault();
      e.returnValue = '';
    }
  }} />

<main>
  {#if tabStore.active.type === "home"}
    <BannerContainer />
  {/if}
  {#if isLoading}
    <div class="loading-bar" aria-label="Loading"></div>
  {/if}
  <PopupOverlay />
  {#if confirmRequest}
    <ConfirmDialog
      message={confirmRequest.message}
      onConfirm={handleConfirmCommand}
      onDismiss={() => { confirmRequest = null; }}
    />
  {/if}
</main>

<style>
  :global(*) {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
  :global(:root) {
    --clr-muted: #82829a;
    --clr-sub:   #9292aa;
    --clr-dim:   #888;
    --clr-kbd:   #999;
    --clr-accent:#7c7c9a;
  }
  :global(body) {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    height: 100vh;
    display: flex;
    flex-direction: column;
  }
  main {
    display: flex;
    flex-direction: column;
    height: 100vh;
    width: 100%;
  }
  .loading-bar {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 3px;
    background: linear-gradient(90deg, #7c7c9a 0%, #a4a4d0 50%, #7c7c9a 100%);
    background-size: 200% 100%;
    animation: bar-slide 1.5s ease-in-out infinite;
    z-index: 1000;
  }
  @keyframes bar-slide {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
</style>
