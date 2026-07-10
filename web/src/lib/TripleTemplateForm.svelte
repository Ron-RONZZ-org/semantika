<script>
  import FormField from "./FormField.svelte";

  /**
   * Dynamic form for triple templates.
   * Loads template params from GET /api/v1/triple-templates/{name},
   * renders input fields, and submits to POST /api/v1/triple-templates/execute.
   * 
   * Props:
   *   data.templateName — template name to load
   *   data.initialData  — pre-filled values
   */
  let { data = {} } = $props();
  let templateName = $derived(data?.templateName || "");
  let initialData = $derived(data?.initialData || {});

  let template = $state(null);
  let loading = $state(true);
  let error = $state("");
  let fieldValues = $state({});
  let formErrors = $state({});
  let submitting = $state(false);

  $effect(() => {
    if (!templateName) return;
    loading = true;
    error = "";
    fetch(`/api/v1/triple-templates/${encodeURIComponent(templateName)}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(t => {
        template = t;
        // Initialize form fields from template params
        const vals = { ...initialData };
        for (const p of t.params || []) {
          if (!(p.name in vals)) vals[p.name] = "";
        }
        fieldValues = vals;
        loading = false;
      })
      .catch(e => {
        error = String(e);
        loading = false;
      });
  });

  function setField(name, val) {
    fieldValues = { ...fieldValues, [name]: val };
    if (formErrors[name]) {
      const next = { ...formErrors };
      delete next[name];
      formErrors = next;
    }
  }

  function fieldInputType(paramType) {
    if (paramType === "number") return "number";
    return "text";
  }

  function fieldPlaceholder(param) {
    if (param.type === "node") return "node ID (e.g. MyNode)";
    if (param.type === "number") return "0";
    return "text value";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errors = {};
    for (const p of template.params) {
      const val = (fieldValues[p.name] || "").trim();
      if (p.required && !val) {
        errors[p.name] = `${p.label || p.name} is required`;
      }
    }
    formErrors = errors;
    if (Object.keys(errors).length > 0) return;

    submitting = true;
    try {
      const resp = await fetch("/api/v1/triple-templates/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: templateName, values: fieldValues }),
      });
      const result = await resp.json();
      // Open result in a popup/tab
      const { tabStore } = await import("./tabStore.svelte.js");
      tabStore.open(result.type || "status", result.title || "Template Result", result.data || result);
    } catch (err) {
      const { tabStore } = await import("./tabStore.svelte.js");
      tabStore.open("error", "Error", { type: "error", data: { message: String(err) } });
    } finally {
      submitting = false;
    }
  }
</script>

<div class="template-form">
  {#if loading}
    <p class="loading-msg">Loading template&hellip;</p>
  {:else if error}
    <p class="error-msg">Failed to load template: {error}</p>
  {:else if template}
    <h3>{template.description || templateName} <span class="tpl-name">({templateName})</span></h3>

    <form onsubmit={handleSubmit}>
      {#each template.params as param}
        <FormField
          label={param.label || param.name}
          hint={param.type}
          required={param.required}
          error={formErrors[param.name]}
        >
          <input
            type={fieldInputType(param.type)}
            id={param.name}
            value={fieldValues[param.name] || ""}
            oninput={(e) => setField(param.name, e.target.value)}
            disabled={submitting}
            placeholder={fieldPlaceholder(param)}
          />
        </FormField>
      {/each}

      {#if template.triples && template.triples.length > 0}
        <div class="triple-preview">
          <h4>Triples to add</h4>
          <ul>
            {#each template.triples as triple}
              <li><code>{triple}</code></li>
            {/each}
          </ul>
        </div>
      {/if}

      <div class="form-actions">
        <button type="submit" disabled={submitting}>
          {submitting ? "Adding triples\u2026" : "Add Triples"}
        </button>
      </div>
    </form>
  {/if}
</div>

<style>
  .template-form { padding: 1rem; }
  .template-form h3 { margin: 0 0 1rem; font-size: 1rem; color: #e0e0e0; }
  .tpl-name { color: #82829a; font-weight: normal; font-size: 0.85rem; }
  .loading-msg, .error-msg { color: #82829a; padding: 1rem; }
  .error-msg { color: #d45; }
  .triple-preview { margin: 0.75rem 0; }
  .triple-preview h4 { font-size: 0.8rem; color: #82829a; margin: 0 0 0.25rem; }
  .triple-preview ul { list-style: none; padding: 0; }
  .triple-preview li {
    font-size: 0.75rem; color: #9292aa; padding: 2px 0;
    font-family: monospace;
  }
  .form-actions { padding-top: 0.5rem; }
  .form-actions button {
    padding: 0.4rem 1rem; background: #3a6a3a; color: #e0e0e0;
    border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem;
  }
  .form-actions button:hover { background: #4a8a4a; }
  .form-actions button:disabled { opacity: 0.5; }
  :global(.template-form input[type="text"]),
  :global(.template-form input[type="number"]) {
    padding: 0.4rem 0.6rem; border: 1px solid #444; border-radius: 4px;
    font-size: 0.85rem; background: #2a2a3e; color: #e0e0e0; outline: none;
  }
  :global(.template-form input:focus) { border-color: #7c7c9a; }
</style>
