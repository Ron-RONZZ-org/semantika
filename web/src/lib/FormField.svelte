<script>
  let { label = "", hint = "", error = "", required = false,
    id = label ? label.toLowerCase().replace(/\s+/g, "-") : "",
    class: className = "", children } = $props();
</script>

<div class="field {className}" class:has-error={!!error} class:is-required={required}>
  {#if label}
    <label for={id}>
      <span class="field-label">{label}</span>
      {#if required}<span class="required-badge">&#9679; required</span>{/if}
      {#if hint}<span class="field-hint">{hint}</span>{/if}
    </label>
  {/if}
  {@render children?.()}
  {#if error}<p class="field-error">{error}</p>{/if}
</div>

<style>
  .field { display: flex; flex-direction: column; gap: 0.25rem;
    padding: 0.3rem 0.4rem; border-radius: 4px; transition: background 0.1s; }
  .field.is-required { background: rgba(200, 68, 68, 0.06); }
  .field.has-error :global(input), .field.has-error :global(select),
  .field.has-error :global(textarea) { border-color: #c44; }
  label { display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; }
  .field-label { font-size: 0.78rem; color: #c0c0c0; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .field-hint { font-weight: 400; text-transform: none; letter-spacing: 0; color: #7c7c9a; font-size: 0.7rem;
    max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
  .required-badge { font-size: 0.68rem; color: #c44; font-weight: 700; text-transform: uppercase;
    background: rgba(200, 68, 68, 0.12); padding: 0.08rem 0.35rem; border-radius: 3px; }
  .field-error { margin: 0; color: #c44; font-size: 0.75rem; }
</style>
