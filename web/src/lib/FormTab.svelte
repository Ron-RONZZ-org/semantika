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
      "node-delete": ["node", "delete"],
      "predicate-add": ["predicate", "add"],
      "predicate-delete": ["predicate", "delete"],
      "predicate-group-add": ["predicate", "group", "add"],
      "triple-add": ["triple", "add"],
      "triple-delete": ["triple", "delete"],
      "triple-modify": ["triple", "modify"],
      "unit-add": ["unit", "add"],
      "proof-add": ["proof", "add"],
      "reset-no-backup": ["reset"],
    };
    if (map[formType]) return map[formType];
    // Dynamic derivation for node-add-* form types
    // e.g., "node-add-attachment-photo" → ["node", "add", "attachment", "photo"]
    // This covers all attachment/media/scholarly variants without hardcoding.
    if (formType.startsWith("node-add-")) {
      return formType.split("-");
    }
    return [];
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

      // Post-submit redirect: close the form and open the list with
      // a highlight animation on the newly created node/predicate.
      const returnType = data?.returnType;
      const returnTokens = data?.returnTokens;
      const returnTitle = data?.returnTitle || "List";
      const returnIdKey = data?.returnIdKey;
      const nodeId = result?.data?.node?.node_id;
      const predId = result?.data?.predicate?.predicate_id;

      if (resp.ok && (nodeId || predId) && returnType && returnTokens) {
        const entityId = nodeId || predId;
        const currentId = tabStore.active?.id;
        if (currentId) tabStore.close(currentId);

        // Fetch fresh list data so the new entity appears in the list
        const listResp = await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: returnTokens, flags: {}, remaining: [] }),
        });
        if (listResp.ok) {
          const listResult = await listResp.json();
          const listData = listResult?.data || listResult || {};

          if (returnIdKey) {
            const existingId = tabStore.findByKey(returnIdKey);
            if (existingId) {
              tabStore.update(existingId, { ...listData, _highlight: entityId });
              tabStore.setActive(existingId);
              return;
            }
          }
          // Fallback: open a new list tab (deduplicates by type via TabView)
          tabStore.open(returnType, returnTitle, { ...listData, _highlight: entityId }, { idKey: returnType });
        } else {
          // List fetch failed, node was still created — go to home
          tabStore.goHome();
        }
        return;
      }

      // Original behavior: show result in a status tab
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
