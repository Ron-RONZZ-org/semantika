<script>
  import { overlayStack } from "@lightercore/ui/overlayStack.svelte.js";

  let {
    onConfigured = () => {},
    onDismiss = () => {},
  } = $props();

  // Register with overlay stack so TabView defers to this modal on ESC/Q
  let _overlayEntry = $state(null);
  $effect(() => {
    _overlayEntry = overlayStack.push("llm-setup-modal", () => onDismiss());
    return () => {
      if (_overlayEntry) overlayStack.remove(_overlayEntry.id);
      _overlayEntry = null;
    };
  });

  let step = $state("checking");
  let providerType = $state("deepseek");
  let apiKey = $state("");
  let baseUrl = $state("");
  let model = $state("");
  let saving = $state(false);
  let error = $state("");

  const PROVIDERS = [
    {
      id: "deepseek",
      name: "DeepSeek",
      baseUrl: "https://api.deepseek.com",
      model: "deepseek-v4-flash",
      desc: "DeepSeek-V4, DeepSeek-R1",
      needsKey: true,
    },
    {
      id: "ollama",
      name: "Ollama (local)",
      baseUrl: "http://localhost:11434/v1",
      model: "llama3.2",
      desc: "Run models locally, no API key needed",
      needsKey: false,
    },
    {
      id: "openai",
      name: "OpenAI",
      baseUrl: "https://api.openai.com/v1",
      model: "gpt-4o",
      desc: "GPT-4o, GPT-4, GPT-3.5",
      needsKey: true,
    },
    {
      id: "custom",
      name: "Custom (OpenAI-compatible)",
      baseUrl: "",
      model: "",
      desc: "Any OpenAI-compatible API",
      needsKey: true,
    },
    {
      id: "_skip",
      name: "Skip",
      desc: "Use ! commands only \u2014 configure LLM later",
      skip: true,
    },
  ];

  let selectedProvider = $state(null);

  $effect(() => {
    if (step === "checking") {
      checkSingleProfile();
    }
  });

  async function checkSingleProfile() {
    try {
      const resp = await fetch("/api/v1/llm/profiles");
      if (resp.ok) {
        const data = await resp.json();
        const profiles = data.profiles || [];
        if (profiles.length === 1) {
          const name = profiles[0].name;
          const loadResp = await fetch(`/api/v1/llm/profiles/${encodeURIComponent(name)}/load`, {
            method: "POST",
          });
          if (loadResp.ok) {
            step = "done";
            selectedProvider = { name: profiles[0].provider_type || name };
            setTimeout(() => onConfigured(), 600);
            return;
          }
        }
      }
    } catch { /* fall through */ }
    step = "select";
  }

  function selectProvider(p) {
    if (p.skip) {
      onDismiss();
      return;
    }
    selectedProvider = p;
    providerType = p.id;
    baseUrl = p.baseUrl;
    model = p.model;
    apiKey = "";
    error = "";

    if (p.id === "ollama") {
      saveConfig();
    } else if (p.id === "custom") {
      step = "custom";
    } else {
      step = "enter-key";
    }
  }

  async function saveConfig() {
    saving = true;
    error = "";
    try {
      const resp = await fetch("/api/v1/llm/configure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: providerType,
          api_key: apiKey,
          base_url: baseUrl,
          model: model,
          temperature: 0.7,
          max_tokens: 2048,
        }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${resp.status}`);
      }
      step = "done";
      // Let the user see the success confirmation, then close
      setTimeout(() => onConfigured(), 800);
    } catch (err) {
      error = err.message || "Failed to save. Check your credentials and try again.";
    } finally {
      saving = false;
    }
  }

  async function handleCustomSave() {
    if (!baseUrl) {
      error = "Base URL is required.";
      return;
    }
    if (!model) {
      error = "Model name is required.";
      return;
    }
    await saveConfig();
  }
</script>

{#if step === "checking"}
  <div class="modal-overlay">
    <div class="modal">
      <div class="modal-header">
        <h2>Configure LLM</h2>
        <p class="subtitle">Checking for saved profiles\u2026</p>
      </div>
    </div>
  </div>

{:else if step === "select"}
  <div class="modal-overlay" onclick={onDismiss} onkeydown={(e) => e.key === "Escape" && onDismiss()} role="button" tabindex="-1" aria-label="Dismiss">
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="0" onkeydown={() => {}}>
      <div class="modal-header">
        <h2>Configure LLM</h2>
        <p class="subtitle">Choose a provider to enable AI chat</p>
      </div>
      <div class="provider-list">
        {#each PROVIDERS as p}
          <button class="provider-card" class:skip-card={p.skip} onclick={() => selectProvider(p)}>
            <span class="provider-name">{p.name}</span>
            <span class="provider-desc">{p.desc}</span>
          </button>
        {/each}
      </div>
    </div>
  </div>

{:else if step === "enter-key"}
  <div class="modal-overlay" onclick={onDismiss} onkeydown={(e) => e.key === "Escape" && onDismiss()} role="button" tabindex="-1" aria-label="Dismiss">
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="0" onkeydown={() => {}}>
      <div class="modal-header">
        <h2>{selectedProvider?.name}</h2>
        <p class="subtitle">Paste your API key to get started</p>
      </div>
      <div class="form">
        <label class="field">
          <span class="field-label">API Key</span>
          <!-- svelte-ignore a11y_autofocus -->
          <input
            type="password"
            class="text-input"
            bind:value={apiKey}
            placeholder="sk-..."
            autofocus
          />
        </label>
        {#if error}
          <p class="error">{error}</p>
          <div class="form-actions">
            <button class="btn-primary" onclick={saveConfig} disabled={saving}>
              {saving ? "Saving\u2026" : "Retry"}
            </button>
            <button class="btn-secondary" onclick={() => { step = "select"; error = ""; }}>Back</button>
          </div>
        {:else}
          <div class="form-actions">
            <button class="btn-primary" onclick={saveConfig} disabled={saving || !apiKey}>
              {saving ? "Saving\u2026" : "Save & Start"}
            </button>
            <button class="btn-secondary" onclick={() => { step = "select"; error = ""; }}>Back</button>
          </div>
        {/if}
      </div>
    </div>
  </div>

{:else if step === "custom"}
  <div class="modal-overlay" onclick={onDismiss} onkeydown={(e) => e.key === "Escape" && onDismiss()} role="button" tabindex="-1" aria-label="Dismiss">
    <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="0" onkeydown={() => {}}>
      <div class="modal-header">
        <h2>Custom Provider</h2>
        <p class="subtitle">Configure any OpenAI-compatible API</p>
      </div>
      <div class="form">
        <label class="field">
          <span class="field-label">Base URL</span>
          <!-- svelte-ignore a11y_autofocus -->
          <input type="text" class="text-input" bind:value={baseUrl} placeholder="https://api.example.com" autofocus />
        </label>
        <label class="field">
          <span class="field-label">Model</span>
          <input type="text" class="text-input" bind:value={model} placeholder="gpt-4o" />
        </label>
        <label class="field">
          <span class="field-label">API Key</span>
          <input type="password" class="text-input" bind:value={apiKey} placeholder="sk-..." />
        </label>
        {#if error}
          <p class="error">{error}</p>
          <div class="form-actions">
            <button class="btn-primary" onclick={handleCustomSave} disabled={saving}>
              {saving ? "Saving\u2026" : "Retry"}
            </button>
            <button class="btn-secondary" onclick={() => { step = "select"; error = ""; }}>Back</button>
          </div>
        {:else}
          <div class="form-actions">
            <button class="btn-primary" onclick={handleCustomSave} disabled={saving || !baseUrl || !model}>
              {saving ? "Saving\u2026" : "Save & Start"}
            </button>
            <button class="btn-secondary" onclick={() => { step = "select"; error = ""; }}>Back</button>
          </div>
        {/if}
      </div>
    </div>
  </div>

{:else if step === "done"}
  <div class="modal-overlay">
    <div class="modal">
      <div class="modal-header">
        <h2>\u2713 Configured</h2>
        <p class="subtitle">{selectedProvider?.name} is ready. You can now chat with the AI.</p>
      </div>
      <div class="form-actions" style="justify-content: center; margin-top: 1rem;">
        <button class="btn-primary" onclick={onConfigured}>Start Chatting</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.15s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  .modal {
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 16px;
    padding: 1.5rem;
    width: 400px;
    max-width: 90vw;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  }
  .modal-header { margin-bottom: 1rem; }
  .modal-header h2 {
    font-size: 1.1rem;
    color: #e0e0e0;
    font-weight: 600;
  }
  .subtitle {
    font-size: 0.8rem;
    color: #7c7c9a;
    margin-top: 0.25rem;
  }
  .provider-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .provider-card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    padding: 0.75rem 1rem;
    background: #2a2a3e;
    border: 1px solid #444;
    border-radius: 10px;
    color: #e0e0e0;
    font-family: inherit;
    font-size: 0.9rem;
    cursor: pointer;
    transition: background 0.1s, border-color 0.1s;
    width: 100%;
    text-align: left;
  }
  .provider-card:hover {
    background: #3a3a5a;
    border-color: #7c7c9a;
  }
  .provider-name { font-weight: 600; }
  .provider-desc { font-size: 0.78rem; color: #7c7c9a; margin-top: 2px; }
  .skip-card {
    margin-top: 0.5rem;
    border-color: #3a3a3a !important;
    background: #22223a !important;
  }
  .skip-card:hover {
    background: #2a2a3e !important;
    border-color: #5a5a7a !important;
  }
  .skip-card .provider-name {
    color: #7c7c9a !important;
    font-weight: 400 !important;
  }
  .form { display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.3rem; }
  .field-label {
    font-size: 0.78rem;
    color: #7c7c9a;
    font-family: monospace;
  }
  .text-input {
    background: #2a2a3e;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 0.6rem 0.8rem;
    color: #e0e0e0;
    font-size: 0.9rem;
    outline: none;
    font-family: monospace;
  }
  .text-input:focus { border-color: #7c7c9a; }
  .error { color: #aa6a6a; font-size: 0.8rem; }
  .form-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
  .btn-primary, .btn-secondary {
    padding: 0.5rem 1rem;
    border-radius: 8px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-primary {
    background: #3a6a3a;
    color: #e0e0e0;
    border-color: #4a8a4a;
    flex: 1;
  }
  .btn-primary:hover { background: #4a8a4a; }
  .btn-primary:disabled { opacity: 0.4; cursor: default; }
  .btn-secondary { background: #2a2a3e; color: #b0b0c0; }
  .btn-secondary:hover { background: #3a3a5a; }
</style>
