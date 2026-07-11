<script>
  /**
   * Re-export of the shared ConfirmDialog from lightercore.
   *
   * semantika previously had its own ConfirmDialog.svelte with hardcoded
   * dark theme.  The shared version in lightercore uses CSS variables
   * instead, so the visual result is identical — no styling change needed.
   *
   * All props are forwarded transparently.
   */
  import SharedConfirmDialog from "@lightercore/ui/ConfirmDialog.svelte";
  let { ...rest } = $props();
</script>

<SharedConfirmDialog {...rest} />
