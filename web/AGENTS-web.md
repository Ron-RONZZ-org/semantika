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
| `commandHistory.svelte.js` | Navigation history with up/down arrow recall |
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
| `StatusPopup.svelte` | Status/result display (node details, triple lists, etc.) |
| `ErrorPopup.svelte` | Error display |
| `LoadingPopup.svelte` | Loading spinner |
| `ConfirmDialog.svelte` | Confirmation dialog for destructive actions |
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
2. `HomeTab.svelte` detects `/` prefix, calls `execute()` from `commandExecutor.js`
3. `commandExecutor.js` calls `POST /api/v1/prompt-commands/execute` with `{name, args}`
4. Backend loads the `.md` file from `~/.config/semantika/commands/`, expands `$1`/`$2`/`$ARGUMENTS`, sends to LLM
5. Response is rendered as chat in the HomeTab

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
