<script>
  import { findNode } from "./commandTree.js";
  import FormField from "./FormField.svelte";

  let { commandPath = [], initialData = {}, onsubmit = async () => {} } = $props();

  let node = $derived(findNode(commandPath));
  let params = $derived(node?.params || []);
  let flags = $derived(node?.flags || []);
  let submitting = $state(false);
  let formErrors = $state({});
  let fieldValues = $state({});

  $effect(() => {
    const vals = { ...initialData };
    for (const p of params) { if (!(p.name in vals)) vals[p.name] = ""; }
    for (const f of flags) {
      if (f.type === "flag") vals[f.name] = initialData[f.name] || false;
      else if (!(f.name in vals)) vals[f.name] = "";
    }
    fieldValues = vals;
  });

  function setField(name, val) {
    fieldValues = { ...fieldValues, [name]: val };
    if (formErrors[name]) { const next = { ...formErrors }; delete next[name]; formErrors = next; }
  }

  function isSensitive(name) { return /password|secret|key|token/i.test(name); }

  function fieldType(flagDef) {
    if (flagDef.type === "number") return "number";
    if (flagDef.type === "date") return "date";
    if (flagDef.type === "flag") return "checkbox";
    if (isSensitive(flagDef.name)) return "password";
    return "text";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errors = {}; const flags_out = {}; let remaining = [];
    for (let i = 0; i < params.length; i++) {
      const val = (fieldValues[params[i].name] || "").trim();
      if (params[i].required && !val) errors[params[i].name] = `${params[i].name} is required`;
      remaining.push(val);
    }
    for (const f of flags) {
      let val = fieldValues[f.name];
      if (f.type === "flag") { if (val) flags_out[f.name] = "true"; }
      else if (val && val !== "") flags_out[f.name] = val;
    }
    formErrors = errors;
    if (Object.keys(errors).length > 0) return;
    submitting = true;
    try { await onsubmit({ tokens: commandPath, flags: flags_out, remaining }); }
    finally { submitting = false; }
  }
</script>

<form onsubmit={handleSubmit} class="dynamic-form">
  {#each params as p}
    <FormField label={p.name} hint={p.type} required={p.required} error={formErrors[p.name]}>
      <input type="text" id={p.name} value={fieldValues[p.name] || ""}
        oninput={(e) => setField(p.name, e.target.value)}
        disabled={submitting} placeholder={p.placeholder || ""} />
    </FormField>
  {/each}

  {#each flags as f}
    <FormField label={f.name} hint={f.help || f.type}>
      {#if f.type === "flag"}
        <label class="checkbox-label">
          <input type="checkbox" checked={fieldValues[f.name] || false}
            onchange={(e) => setField(f.name, e.target.checked)} disabled={submitting} />
          {f.help || f.name}
        </label>
      {:else}
        <input type={fieldType(f)} id={f.name} value={fieldValues[f.name] || ""}
          oninput={(e) => setField(f.name, e.target.value)}
          disabled={submitting} placeholder={f.help || ""} />
      {/if}
    </FormField>
  {/each}

  <div class="form-actions">
    <button type="submit" disabled={submitting}>{submitting ? "Saving\u2026" : "Save"}</button>
  </div>
</form>

<style>
  .dynamic-form { display: flex; flex-direction: column; gap: 0.75rem; padding: 1rem; }
  .checkbox-label { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; font-size: 0.9rem; color: #e0e0e0; }
  .form-actions { display: flex; gap: 0.5rem; padding-top: 0.5rem; }
  .form-actions button { padding: 0.4rem 1rem; background: #3a6a3a; color: #e0e0e0;
    border: none; border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
  .form-actions button:hover { background: #4a8a4a; }
  .form-actions button:disabled { opacity: 0.5; }
  :global(.dynamic-form input[type="text"]),
  :global(.dynamic-form input[type="number"]),
  :global(.dynamic-form input[type="password"]),
  :global(.dynamic-form input[type="date"]) {
    padding: 0.4rem 0.6rem; border: 1px solid #444; border-radius: 4px; font-size: 0.85rem;
    background: #2a2a3e; color: #e0e0e0; outline: none;
  }
  :global(.dynamic-form input:focus) {
    border-color: #7c7c9a;
  }
</style>
