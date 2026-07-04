<script>
  /** FormTab — routes form types to specific form components.
   *  Ported from lighterbird's FormTab.svelte.
   */
  import { tabStore } from "./tabStore.svelte.js";
  import DynamicForm from "./DynamicForm.svelte";

  let { data = {} } = $props();
  let formType = $derived(data?.form || "");
  let initialData = $derived(data?.initialData || {});
  let commandPath = $derived(data?.commandPath || _inferCommandPath(formType));
  let submitting = $state(false);

  function _inferCommandPath(formType) {
    const map = {
      "node-add": ["node", "add"],
      "predicate-add": ["predicate", "add"],
      "triple-add": ["triple", "add"],
      "unit-add": ["unit", "add"],
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
      tabStore.open(result.type || "status", "Result", result);
    } catch (err) {
      tabStore.open("error", "Error", { type: "error", data: { message: String(err) } });
    } finally { submitting = false; }
  }
</script>

<div class="form-tab">
  <h3>{formType.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</h3>
  <DynamicForm {commandPath} {initialData} onsubmit={handleFormSubmit} />
</div>

<style>
  .form-tab { padding: 1rem; }
  .form-tab h3 { margin: 0 0 1rem; font-size: 1rem; color: #333; }
</style>
