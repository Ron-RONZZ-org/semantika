<script>
  /** FormField — unified form field wrapper with label, hint, error.
   *  Ported from lighterbird's FormField.svelte.
   */
  let { label = "", hint = "", error = "", required = false,
    id = label ? label.toLowerCase().replace(/\s+/g, "-") : "",
    class: className = "", children } = $props();
</script>

<div class="field {className}" class:has-error={!!error}>
  {#if label}
    <label for={id}>
      <span class="field-label">{label}</span>
      {#if required}<span class="required-badge">required</span>{/if}
      {#if hint}<span class="field-hint">{hint}</span>{/if}
    </label>
  {/if}
  {@render children?.()}
  {#if error}<p class="field-error">{error}</p>{/if}
</div>

<style>
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field.has-error :global(input), .field.has-error :global(select), .field.has-error :global(textarea) { border-color: #c44; }
  label { display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; }
  .field-label { font-size: 0.78rem; color: #666; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .field-hint { font-weight: 400; text-transform: none; letter-spacing: 0; color: #999; font-size: 0.7rem; }
  .required-badge { font-size: 0.65rem; color: #c44; font-weight: 600; text-transform: uppercase; }
  .field-error { margin: 0; color: #c44; font-size: 0.75rem; }
</style>
