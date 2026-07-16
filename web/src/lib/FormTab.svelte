<script>
  import { tabStore } from "./tabStore.svelte.js";
  import DynamicForm from "./DynamicForm.svelte";
  import TripleTemplateForm from "./TripleTemplateForm.svelte";

  let { data = {} } = $props();
  let formType = $derived(data?.form || "");
  let initialData = $derived(data?.initialData || {});
  let commandPath = $derived(data?.commandPath || _inferCommandPath(formType));
  let submitting = $state(false);

  function _inferCommandPath(formType) {
    const map = {
      "node-add": ["node", "add", "concept"],
      "node-add-photo": ["node", "add", "photo"],
      "node-add-video": ["node", "add", "video"],
      "node-add-file": ["node", "add", "file"],
      "node-add-code": ["node", "add", "code"],
      "node-delete": ["node", "delete"],
      "predicate-add": ["predicate", "add"],
      "predicate-delete": ["predicate", "delete"],
      "triple-add": ["triple", "add"],
      "triple-delete": ["triple", "delete"],
      "triple-modify": ["triple", "modify"],
      "unit-add": ["unit", "add"],
      "proof-add": ["proof", "add"],
      "predicate-group-add": ["predicate", "group", "add"],
      "reset-no-backup": ["reset"],
    };
    return map[formType] || [];
  }

  async function handleFormSubmit(payload) {
    if (submitting) return;
    submitting = true;
    try {
      const resp = await fetch("/api/v1/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await resp.json();
      tabStore.open(result.type || "status", result.title || "Result", result.data || result);
    } catch (err) {
      tabStore.open("error", "Error", { type: "error", data: { message: String(err) } });
    } finally { submitting = false; }
  }
</script>

<div class="form-tab">
  <h3>{formType.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</h3>
  {#if formType.startsWith("triple-template-")}
    <TripleTemplateForm {data} />
  {:else}
    <DynamicForm {commandPath} {initialData} onsubmit={handleFormSubmit} />
  {/if}
</div>

<style>
  .form-tab { padding: 1rem; }
  .form-tab h3 { margin: 0 0 1rem; font-size: 1rem; color: #e0e0e0; text-transform: capitalize; }
</style>
