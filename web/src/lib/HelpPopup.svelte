<script>
  /**
   * Help tab — interactive command reference.
   *
   * Props: data from the backend !help response:
   *   { groups: {domain: [command, ...]}, total, group_count }  — full reference
   *   { command: {path, canonical, description, params, flags} } — single command
   *   { error: string } — command not found
   */
  let { data = {} } = $props();

  let groups = $state({});
  let expandedGroups = $state(new Set());
  let expandedCommands = $state(new Set());
  let filterText = $state("");

  // Initialise from props
  $effect(() => {
    if (data && data.groups) {
      groups = data.groups;
      // Auto-expand all groups on first load
      expandedGroups = new Set(Object.keys(data.groups));
    }
  });

  /** Filtered domain keys */
  let visibleDomains = $derived.by(() => {
    if (!filterText.trim()) return Object.keys(groups);
    const q = filterText.toLowerCase();
    return Object.entries(groups)
      .filter(([, cmds]) =>
        cmds.some((c) => matchCommand(c, q)),
      )
      .map(([domain]) => domain);
  });

  function matchCommand(cmd, q) {
    const canonical = cmd.canonical ? cmd.canonical.toLowerCase() : "";
    const desc = cmd.description ? cmd.description.toLowerCase() : "";
    if (canonical.includes(q) || desc.includes(q)) return true;
    if (cmd.path && cmd.path.some((p) => p.toLowerCase().includes(q))) return true;
    if (cmd.params) {
      for (const p of cmd.params) {
        if ((p.name && p.name.toLowerCase().includes(q)) ||
            (p.description && p.description.toLowerCase().includes(q))) return true;
      }
    }
    if (cmd.flags) {
      for (const f of cmd.flags) {
        if ((f.name && f.name.toLowerCase().includes(q)) ||
            (f.help && f.help.toLowerCase().includes(q))) return true;
      }
    }
    return false;
  }

  function toggleGroup(domain) {
    const next = new Set(expandedGroups);
    if (next.has(domain)) next.delete(domain);
    else next.add(domain);
    expandedGroups = next;
  }

  function toggleCommand(canonical) {
    const next = new Set(expandedCommands);
    if (next.has(canonical)) next.delete(canonical);
    else next.add(canonical);
    expandedCommands = next;
  }

  function paramSummary(cmd) {
    const parts = [];
    if (cmd.params && cmd.params.length) {
      for (const p of cmd.params) {
        parts.push(p.required ? `<${p.name}>` : `[${p.name}]`);
      }
    }
    if (cmd.flags && cmd.flags.length) {
      parts.push("[--flags]");
    }
    return parts.length ? parts.join(" ") : "";
  }
</script>

<div class="help-tab">
  {#if data.error}
    <!-- ── Error state ──────────────────────────────────────────────── -->
    <div class="help-error">
      <span class="error-icon">⚠</span>
      <p>{data.error}</p>
      <p class="hint">Type <code>!help</code> to see all available commands.</p>
    </div>

  {:else if data.command}
    <!-- ── Single command detail ────────────────────────────────────── -->
    {@const cmd = data.command}
    <div class="help-single">
      <h3><code>{cmd.canonical || ("!" + (cmd.path || []).join(" "))}</code></h3>
      {#if cmd.description}
        <p class="cmd-desc">{cmd.description}</p>
      {/if}

      {#if cmd.params && cmd.params.length}
        <h4>Parameters</h4>
        <dl class="param-list">
          {#each cmd.params as p}
            <div class="param-row">
              <dt>
                <code>{p.name}</code>
                {#if p.required}<span class="badge required">required</span>{/if}
              </dt>
              <dd>{p.description || p.name}</dd>
            </div>
          {/each}
        </dl>
      {/if}

      {#if cmd.flags && cmd.flags.length}
        <h4>Flags</h4>
        <dl class="param-list">
          {#each cmd.flags as f}
            <div class="param-row">
              <dt><code>--{f.name}</code></dt>
              <dd>{f.help || f.name}</dd>
            </div>
          {/each}
        </dl>
      {/if}
    </div>

  {:else}
    <!-- ── Full grouped reference ───────────────────────────────────── -->
    <div class="help-header">
      <h3>Command Reference</h3>
      <span class="help-count">{data.total || "?"} commands in {data.group_count || "?"} groups</span>
    </div>

    <div class="help-filter">
      <input
        type="text"
        placeholder="Filter commands by name, description, or flag…"
        bind:value={filterText}
        aria-label="Filter commands"
      />
    </div>

    <div class="help-groups">
      {#each visibleDomains as domain}
        {@const cmds = groups[domain]}
        {@const isOpen = expandedGroups.has(domain)}
        <div class="group" class:expanded={isOpen}>
          <button class="group-header" onclick={() => toggleGroup(domain)}>
            <span class="group-arrow">{isOpen ? "▾" : "▸"}</span>
            <span class="group-name">{domain}</span>
            <span class="group-count">{cmds.length}</span>
          </button>
          {#if isOpen}
            <div class="group-body">
              {#each cmds as cmd}
                {@const key = cmd.canonical || cmd.path.join(".")}
                {@const isCmdOpen = expandedCommands.has(key)}
                <div class="cmd" class:expanded={isCmdOpen}>
                  <button class="cmd-header" onclick={() => toggleCommand(key)}>
                    <span class="cmd-arrow">{isCmdOpen ? "▾" : "▸"}</span>
                    <code class="cmd-canonical">{cmd.canonical || ("!" + cmd.path.join(" "))}</code>
                    {#if cmd.description}
                      <span class="cmd-desc-preview">{cmd.description}</span>
                    {/if}
                  </button>
                  {#if isCmdOpen}
                    <div class="cmd-body">
                      {#if cmd.params && cmd.params.length}
                        <div class="cmd-section">
                          <strong>Parameters:</strong>
                          {#each cmd.params as p}
                            <div class="detail-row">
                              <code>{p.name}</code>
                              {#if p.required}<span class="badge required">required</span>{/if}
                              <span class="detail-desc">{p.description || ""}</span>
                            </div>
                          {/each}
                        </div>
                      {/if}
                      {#if cmd.flags && cmd.flags.length}
                        <div class="cmd-section">
                          <strong>Flags:</strong>
                          {#each cmd.flags as f}
                            <div class="detail-row">
                              <code>--{f.name}</code>
                              <span class="detail-desc">{f.help || ""}</span>
                            </div>
                          {/each}
                        </div>
                      {/if}
                      {#if (!cmd.params || !cmd.params.length) && (!cmd.flags || !cmd.flags.length)}
                        <span class="no-details">No parameters or flags.</span>
                      {/if}
                    </div>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    {#if visibleDomains.length === 0}
      <div class="no-results">
        No commands match "<code>{filterText}</code>".
        <button class="clear-btn" onclick={() => filterText = ""}>Clear filter</button>
      </div>
    {/if}
  {/if}

  <div class="help-footer">
    <p>
      <strong>Tip:</strong> Type any <code>!command</code> in the bar above to execute it,
      or use <code>/name</code> for custom prompt commands.
      Press <kbd>h</kbd> for keyboard shortcuts.
    </p>
  </div>
</div>

<style>
  .help-tab {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem 1rem;
    color: #e0e0e0;
    font-size: 0.85rem;
  }

  /* ── Header ──────────────────────────────────────────────── */
  .help-header {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
  }
  .help-header h3 {
    margin: 0;
    color: #e0e0e0;
    font-size: 1rem;
  }
  .help-count {
    color: #7c7c9a;
    font-size: 0.78rem;
  }

  /* ── Filter ──────────────────────────────────────────────── */
  .help-filter {
    margin-bottom: 0.75rem;
  }
  .help-filter input {
    width: 100%;
    padding: 0.4rem 0.6rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #22223a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.82rem;
    box-sizing: border-box;
  }
  .help-filter input::placeholder { color: #666; }
  .help-filter input:focus {
    outline: none;
    border-color: #7c7c9a;
  }

  /* ── Groups ──────────────────────────────────────────────── */
  .help-groups {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .group {
    border: 1px solid #2a2a3e;
    border-radius: 6px;
    overflow: hidden;
  }
  .group-header {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.45rem 0.6rem;
    background: #1e1e32;
    border: none;
    color: #c0c0c0;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    text-align: left;
    transition: background 0.1s;
  }
  .group-header:hover { background: #22223a; }
  .group-name { font-weight: 600; text-transform: capitalize; }
  .group-count {
    margin-left: auto;
    color: #7c7c9a;
    font-size: 0.75rem;
  }
  .group-arrow { color: #7c7c9a; font-size: 0.7rem; width: 1rem; }
  .group-body {
    border-top: 1px solid #2a2a3e;
  }

  /* ── Commands ────────────────────────────────────────────── */
  .cmd { border-bottom: 1px solid #222; }
  .cmd:last-child { border-bottom: none; }
  .cmd-header {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.35rem 0.6rem 0.35rem 1.8rem;
    background: #1a1a2e;
    border: none;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.82rem;
    cursor: pointer;
    text-align: left;
    transition: background 0.1s;
  }
  .cmd-header:hover { background: #22223a; }
  .cmd-arrow { color: #555; font-size: 0.65rem; width: 0.8rem; flex-shrink: 0; }
  .cmd-canonical { color: #7fc; white-space: nowrap; }
  .cmd-desc-preview {
    color: #999;
    font-size: 0.78rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-left: auto;
    max-width: 40%;
  }
  .cmd-body {
    padding: 0.4rem 0.6rem 0.5rem 2.6rem;
    font-size: 0.8rem;
    background: #16162a;
    border-top: 1px solid #222;
  }
  .cmd-section {
    margin-bottom: 0.4rem;
  }
  .cmd-section strong {
    color: #aaa;
    font-size: 0.75rem;
    display: block;
    margin-bottom: 0.2rem;
  }
  .detail-row {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
    padding: 0.15rem 0;
    font-size: 0.78rem;
  }
  .detail-row code { color: #c8a0f0; background: none; padding: 0; }
  .detail-desc { color: #999; }
  .no-details { color: #666; font-style: italic; }
  .badge {
    display: inline-block;
    font-size: 0.62rem;
    padding: 1px 5px;
    border-radius: 3px;
    font-family: sans-serif;
  }
  .badge.required {
    background: #5a2a2a;
    color: #e88;
  }

  /* ── Single command ──────────────────────────────────────── */
  .help-single h3 { margin: 0 0 0.5rem; color: #e0e0e0; }
  .help-single code { color: #7fc; }
  .help-single .cmd-desc { color: #ccc; margin: 0 0 1rem; }
  .help-single h4 {
    margin: 0.75rem 0 0.3rem;
    color: #aaa;
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .help-single .param-list { margin: 0; }
  .param-row {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    padding: 0.2rem 0;
  }
  .param-row dt { flex-shrink: 0; min-width: 8rem; }
  .param-row dt code { color: #c8a0f0; }
  .param-row dd { margin: 0; color: #999; }

  /* ── Error ────────────────────────────────────────────────── */
  .help-error {
    text-align: center;
    padding: 2rem 1rem;
    color: #e88;
  }
  .help-error .error-icon { font-size: 1.5rem; }
  .help-error .hint { color: #888; font-size: 0.8rem; margin-top: 0.5rem; }
  .help-error .hint code { color: #7fc; }

  /* ── No results ───────────────────────────────────────────── */
  .no-results {
    text-align: center;
    padding: 1.5rem;
    color: #888;
  }
  .no-results code { color: #7fc; }
  .clear-btn {
    background: none;
    border: 1px solid #444;
    color: #aaa;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.78rem;
    margin-left: 0.5rem;
  }
  .clear-btn:hover { border-color: #7c7c9a; color: #e0e0e0; }

  /* ── Footer ───────────────────────────────────────────────── */
  .help-footer {
    margin-top: 1rem;
    padding-top: 0.6rem;
    border-top: 1px solid #2a2a3e;
    font-size: 0.78rem;
    color: #7c7c9a;
  }
  .help-footer code { color: #7fc; font-size: 0.75rem; }
  .help-footer p { margin: 0; }
  .help-footer kbd {
    display: inline-block;
    padding: 1px 4px;
    font-size: 0.65rem;
    font-family: monospace;
    background: #222;
    border: 1px solid #444;
    border-radius: 3px;
    color: #c0c0c0;
  }
</style>
