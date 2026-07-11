# AGENTS-web.md — Web Frontend Agent Instructions

## Summary
Svelte 5 SPA frontend — command-bar UI with rich result rendering for the Semantika knowledge graph.

## Purpose and Expected Behavior
- **Command bar**: Always-visible input at the top; `!` prefix triggers command mode; `/` prefix triggers prompt commands; natural text triggers LLM chat
- **Autocomplete**: As-you-type suggestions for:
  - `!` commands (fetched from `GET /api/v1/command/tree`)
  - `/` prompt commands (fetched from `GET /api/v1/prompt-commands/list`)
  - Node IDs and predicate IDs (via command engine level-N completions)
- **Result area**: Shows command results (tables, forms, graph visualizations, chat responses, status messages)
- **Tab system**: Multi-tab result area with pinned Home tab — each tab type has a dedicated component
- **Form popups**: Fillable forms for `add`/`modify` commands when required params are missing
- **Graph visualization**: Interactive graph view (force-directed layout) for exploring relationships
- **Katex rendering**: Mathematical formulas rendered inline in results
- **Code block rendering**: Syntax-highlighted code snippets in results
- **Locale**: Persistent locale setting synced with backend `GET/PATCH /api/v1/user/config`

## Input Modes
1. `!command` — built-in operations (`!node add`, `!triple list`, `!backup now`, etc.)
2. `/name [args...]` — user-defined prompt command from `~/.config/semantika/commands/*.md`
3. Natural text — free-form chat with the built-in LLM

## Key Frontend Files

| File | Purpose |
|------|---------|
| `App.svelte` | Root layout — command bar + result area + confirmation dialog |
| `ChatInput.svelte` | Input field with command/prompt/chat mode detection |
| `HomeTab.svelte` | Main home view — LLM chat, prompt commands, command dispatch |
| `HomeHeader.svelte` | Header bar with locale badge, keyboard shortcut trigger |
| `TabView.svelte` | Multi-tab result container |
| `MessageList.svelte` | Chat message rendering in HomeTab |
| `commandEngine.js` | Level-by-level command autocomplete engine |
| `commandTree.js` | Command hierarchy fetched from backend; also hosts `promptCommands` array and `initPromptCommands()` |
| `commandExecutor.js` | Routes input to !command or / prefix, normalizes response types |
| `commandRouter.js` | Maps response types to tab/component display |
| `parser.js` | Tokenizer for !commands; `parsePromptCommand()` for / prefix |
| `formatCommand.js` | Format `{tokens, flags}` → human-readable command string |
| `commandHistory.svelte.js` | Navigation history with up/down arrow recall |
| `optimisticStore.svelte.js` | Optimistic UI helpers — snapshot/rollback for instant tab data updates |
| `popupStore.svelte.js` | Popup/overlay state management |
| `tabStore.svelte.js` | Multi-tab state management (pinned home, open/close/update) |
| `bannerStore.svelte.js` | Banner notification state |
| `dirtyFormStore.svelte.js` | Track unsaved changes in open forms |
| `userConfig.svelte.js` | Locale/preferences store — syncs with backend on init |
| `keyboardShortcuts.svelte.js` | Global keyboard shortcut registry |
| `markdown.js` | Markdown-to-HTML rendering |

## UI Components

| Component | Purpose |
|-----------|---------|
| `NodeListTab.svelte` | Searchable node list with selection, batch delete |
| `PredicateListTab.svelte` | Searchable predicate list with selection, batch delete |
| `TripleListTab.svelte` | Filterable triple list (by subject/predicate) |
| `DynamicForm.svelte` | Generic form builder for command params |
| `FormTab.svelte` | Wrapper for DynamicForm in a tab |
| `FormField.svelte` | Individual form field with validation |
| `PopupOverlay.svelte` | Modal overlay container |
| `StatusPopup.svelte` | Status/result display (node details, triple lists, etc.). Also handles **prompt file viewing** — when data contains ``details`` and ``_edit_name`` fields, renders the prompt content in a scrollable ``<pre>`` block with an **Edit** button that opens an inline editor overlay. |
| `ErrorPopup.svelte` | Error display |
| `LoadingPopup.svelte` | Loading spinner |
| `ConfirmDialog.svelte` | LLM action approval dialog — per-item approve/reject with feedback, full command display, no truncation |
| `formatCommand.js` | Utility: format `{tokens, flags}` → human-readable command string |
| `HelpPopup.svelte` | Command help overlay |
| `KeyboardShortcutOverlay.svelte` | Keyboard shortcuts reference |
| `LlmSetupModal.svelte` | Multi-step LLM provider configuration wizard |
| `GraphView.svelte` | Interactive force-directed graph visualization |
| `QuizPanel.svelte` | Multiple-choice quiz for review sessions |
| `BannerContainer.svelte` | Inline notification banners |

## Autocomplete Flow

1. On startup, `initCommandTree()` fetches `GET /api/v1/command/tree`
2. `initPromptCommands()` fetches `GET /api/v1/prompt-commands/list` and appends a virtual `/` root node
3. `initLocale()` fetches `GET /api/v1/user/config` for locale
4. As user types, `ChatInput.svelte` detects mode (`!`, `/`, or plain text)
5. `commandEngine.js` provides level-by-level completions for `!` commands
6. `getPromptCompletions()` provides completions for `/` prompt commands

## Prompt Command Flow

1. User types `/command-name arg1 arg2` in input
2. `HomeTab.svelte` detects `/` prefix, calls `POST /api/v1/prompt-commands/expand` with `{name, args}`
3. Backend loads the `.md` file, expands `$1`/`$2`/`$ARGUMENTS`, returns the expanded template text
4. An **expanded prompt preview dialog** appears showing the full template text
5. User clicks **Send to LLM** — the expanded text is sent as a normal plain-text message to `POST /api/v1/llm/chat`
6. LLM responds normally; tool calls are gated by ConfirmDialog if write-level

## LLM Action Approval Flow (ConfirmDialog)

When the LLM issues write-level tool calls, they are gated behind user confirmation:

1. Backend returns `{"type": "confirm_tool", "session_id", "batch": [...]}`
2. `ConfirmDialog.svelte` opens with per-item controls:
   - Each tool call shows full command with flags (no truncation)
   - **[Approve]** / **[Tell LLM what to do instead…]** buttons per item
   - Global **[Approve All]** / **[Tell LLM what to do instead (global)…]** buttons
   - **[Submit Decisions]** sends per-item decisions + feedback to the resume endpoint
3. On submit, `POST /api/v1/llm/chat/resume` (or `/api/v1/prompt-commands/execute/resume`) is called with:
   - `decisions: {index: true/false}` — per-item approval
   - `feedback: {index: "string"} | "string"` — per-item or global user feedback
4. The backend injects a summary of rejected tools + feedback as a user message before resuming the tool loop
5. Rejected tool results include the user's feedback: `"User rejected !cmd, with the feedback: {feedback}"`

### ConfirmDialog Props

| Prop | Type | Description |
|------|------|-------------|
| `message` | string | Dialog heading message |
| `batch` | `Array<{index, tokens, flags, description}>` | Tool calls needing approval |
| `onSubmit` | `(decisions, feedback) => void` | Called with per-item decisions + feedback |
| `onDismiss` | `() => void` | Called when dialog is closed/cancelled |

## FormatCommand Utility

`web/src/lib/formatCommand.js` exports `formatCommand(item)` which renders a `{tokens, flags}` object into a human-readable command string like `!node add --label Alice`. Used by `ConfirmDialog.svelte`.

## Constraints and Invariants
- Routes handled client-side via svelte-spa-router
- Command metadata fetched dynamically from `GET /api/v1/command/tree` on startup — never hardcoded
- Prompt commands fetched dynamically from `GET /api/v1/prompt-commands/list`
- Locale fetched from `GET /api/v1/user/config`, falls back to browser language
- No hardcoded command tree — the frontend is driven by backend metadata

## Shared UI Components (`@lightercore/ui`)

Several files in `web/src/lib/` are **re-export wrappers** — the canonical implementation lives in `lightercore/web/src/lib/` (published as `@lightercore/ui` on the npm `file:` dependency path).

### Import convention

```js
// Correct: import directly from @lightercore/ui when possible
import { banner } from "@lightercore/ui/bannerStore.svelte.js";

// Also correct: import from local re-export for backward compat
import { banner } from "./bannerStore.svelte.js";
```

### Currently shared modules

| Local file | Re-exports from `@lightercore/ui` | Type |
|------------|-----------------------------------|------|
| `bannerStore.svelte.js` | `banner` | Reactive store |
| `keyboardShortcuts.svelte.js` | `registerShortcuts`, `getAllShortcuts`, `getScopeShortcuts`, `normalizeKey`, `isInputFocused` | Reactive store |
| `dirtyFormStore.svelte.js` | `dirtyFormStore`, `createFormGuard` | Reactive store |
| `tabStore.svelte.js` | `tabStore` | Reactive store |
| `listTabFormat.js` | `formatListItemDate`, `truncate`, `preview`, `getLabel`, `shortId` | Utility functions |
| `listTabSelection.svelte.js` | `createCopyState`, `createSelectionManager` | Reactive utility |
| `listTabShared.svelte.js` | barrel of above | Barrel |
| `BannerContainer.svelte` | imports `bannerStore` from `@lightercore/ui` | Svelte component |

### Adding shared code

Before adding a new store, utility function, or UI component:
1. Check if a similar component exists in lighterbird or lightercore.
2. If it's shareable, add the canonical version to `lightercore/web/src/lib/`.
3. Add a re-export wrapper in this directory.
4. Add tests in lightercore.
5. See `lightercore/AGENTS.md` → Migration Policy (Svelte/JS) for the detailed process.

### Not yet extracted (future phases)

These components are identified as shareable but need behavioral alignment before extraction:
- `FormField.svelte`, `ConfirmDialog.svelte`, `DynamicForm.svelte`
- `MultiEntryField.svelte` (doesn't exist in semantika yet — add from lightercore when needed)
- `ListTabBase.svelte` (new abstraction for list tabs)

## Optimistic UI Pattern

Write operations (deletes, toggles, simple mutations) should update the UI **immediately** and fire the API call in the background, rolling back on failure. This eliminates the ~1-2s perceived lag from synchronous round-trips.

### When to use
- **Safe**: Deletes, renames, toggles, trash operations — low-risk DB writes
- **NOT safe**: LLM interactions, multi-step creates, confirmation-gated commands, file I/O, backup restore

### Pattern

```js
import { opt } from "./optimisticStore.svelte.js";
import { banner } from "./bannerStore.svelte.js";

async function handleDelete(ids) {
  // 1. Optimistic removal from tab data (instant)
  const rollback = opt.removeFromTab(tabStore.active.id, ids, getKey, "nodes");
  
  try {
    // 2. Fire API calls in background
    for (const id of ids) {
      const resp = await fetch(`/api/v1/graph/nodes/${id}`, { method: "DELETE" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    }
  } catch (err) {
    // 3. On failure: rollback + banner error
    rollback();
    banner.show(`Delete failed: ${err.message}`, "error");
    throw err; // keep selection state for retry
  }
  // On success: no-op — tab data already updated
}
```

### `opt` API

| Method | Purpose |
|--------|---------|
| `removeFromTab(tabId, ids, getKey, field)` | Remove items from tab data; returns rollback fn |
| `mutateTab(tabId, mutator)` | Arbitrary mutation on tab data with rollback |

### Rules
- Always provide a rollback function and call it on API failure
- Always show an error banner when rollback occurs (so the user knows the operation actually failed)
- Re-throw the error so the caller (selection manager, command executor) can manage its own state
- Prefer `removeFromTab` over raw `tabStore.update` for deletes — it handles all data shapes (plain array, `{nodes: [...]}`, `{data: [...]}`)

## Documentation Reference
- lighterbird's web frontend: `../lighterbird/web/` for proven patterns
- lightercore's UI package: `../../lightercore/web/` for canonical shared components

## Domain-Specific Rules for Agents
- **Graph view component**: Use vis.js or D3-force for interactive graph visualization. Nodes are draggable, clickable. Edges show predicate labels.
- **Katex rendering**: Use `katex` npm package. Render in result panels when triples or nodes contain formula data.
- **Code blocks**: Use `highlight.js` or similar for syntax highlighting in triple literal display.
- **Command bar autocomplete**: Must suggest node IDs and predicate IDs as the user types, not just command names.
- **Form popups**: `NodeAddForm`, `TripleAddForm`, `PredicateAddForm` — each maps to a `!command` with missing params.
- **Prompt command autocomplete**: The `/` prefix shows all available prompt commands from the backend. After selecting a name, show placeholder hints for positional args.
- **Locale**: The locale badge in HomeHeader lets users switch language. Sync via `PATCH /api/v1/user/config`.
- **Shared components**: Before modifying a re-export file, check if the change should go into `@lightercore/ui` instead. Canonical implementations are in lightercore.
- Follow the same component patterns as lighterbird: `FormField.svelte`, `MultiEntryField.svelte` for shared form components.

## GUI Style — Imitate Existing Components

**Do not write custom CSS from scratch.** All new UI components must imitate the styling patterns found in these canonical source files:

| Pattern | Reference file | Key elements to imitate |
|---------|---------------|------------------------|
| Toolbar buttons | `lighterbird/web/src/lib/EmailListToolbar.svelte` | `.tool-btn` class, `<kbd>` shortcuts, flex `left/center/right` layout |
| Dialogs/overlays | `lighterbird/web/src/lib/AdvancedSearchDialog.svelte` | `.overlay` + `.dialog` pattern, close on backdrop click |
| Forms | `DynamicForm.svelte` | Field layout, label/input spacing, validation errors |
| Graph visualization | `GraphView.svelte` | Node/edge rendering, drag interaction |
| Colors | Any `.svelte` file in `web/src/lib/` | Dark theme: `#1a1a2e` bg, `#e0e0e0` text, `#444` borders |

**Rules to follow:**
- Use `font-family: monospace` on all structural elements
- Use `border-radius: 4px` for buttons/inputs, `10px` for dialogs
- All interactive elements must be keyboard-reachable
- Animations under 150ms; no keyframe animations on structural elements
- **Never duplicate CSS patterns** — import shared components from `@lightercore/ui` or `web/src/lib/` instead of re-creating them
- If you need a new component, model it after the closest existing component above
