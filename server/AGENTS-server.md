# AGENTS-server.md — Server Module Agent Instructions

## Summary
FastAPI web server: application factory, API routes, middleware, command engine, LLM integration, prompt commands, user configuration.

## Purpose and Expected Behavior
- `app.py` — `create_app()` factory that registers all routers and static file serving.
- **System prompt — two-file model**: The canonical Semantika system prompt lives in ``llm/system_prompt.py``.
  - ``~/.config/semantika/system_prompt.md`` — the base prompt (app's operational instructions).  Auto-seeded on first access.
  - ``~/.config/semantika/AGENTS.md`` — user's custom style/naming conventions.  Auto-seeded and **appended** to the base prompt.
  - Both the chat endpoint and prompt command endpoints call :func:`load_system_prompt` which returns the combined result.
  - Never hardcode or duplicate the prompt text — always import from ``llm/system_prompt.py``.
- **Raw SQL query limit**: The ``POST /api/v1/query/raw`` endpoint rejects queries longer than ``MAX_RAW_QUERY_LENGTH`` (10,000 chars) to prevent resource exhaustion.
- **SPARQL 1.1 Protocol**: ``GET/POST /api/v1/query/sparql`` — standard SPARQL endpoint backed by an Oxigraph RocksDB cache. Supports SELECT, ASK, CONSTRUCT, DESCRIBE. Results are enriched with human-readable labels from SQLite. The SPARQL engine is lazy-initialised on first query. ``!sparql query`` and ``!sparql status`` commands available.

## Domain-Specific Rules for Agents
- **Command response types**: `status` (simple message), `form-required` (redirect to GUI form), `table` (data table), `graph` (graph visualization data), `help` (auto-generated command reference, opens a help tab), `error`
- **Turn prompts use named-only expansion**: ``_expand_turn_prompt`` uses pure ``str.replace()`` with a dict of named variables (e.g. ``$TEMPLATE_DESCRIPTION``, ``$STYLE_EXAMPLE``, ``$ARGUMENTS``). Turn prompts do **not** use positional ``$1``/``$2`` expansion.
- **Context store (``!context.get``)**: Multi-turn flows use a per-session in-memory context store at ``handlers/context.py``. After each turn, the dispatch wrapper (``_make_context_dispatch_wrapper``) automatically collects created/found entities into the context via ``collect_into_context()``. The LLM retrieves exact IDs via ``!context.get --type all`` (READ-level, no HITL).
- **Template flow**: Two-turn flow in ``prompt_commands_helpers.py``. T1 discovers/creates predicates via ``predicate.search`` + ``predicate.add``. T2 uses ``context.get`` to retrieve predicate IDs, generates YAML, and saves via ``template.save`` (with HITL). Both turns gate WRITE tools behind confirmation.
- **Text-to-triples flow** (``/text-to-triples`` or ``/ttt``): Three-turn flow. T1 discovers/creates nodes. T2 discovers templates + predicates. T3 creates triples with post-loop validation (auto-corrective prompts for invalid references, max 3 rounds).
- **Style example injection**: ``_get_style_example()`` scans ``~/.config/semantika/templates/*.{yaml,yml}`` and returns the most recently modified template as a YAML example for ``/template`` turn 2.
- **``!template use``**: Root-level command that applies a template to create nodes from labels and then triples. Handles ``type: node`` params by parsing labels (plain text, ``LANG::TEXT``, or JSON dicts), searching for existing nodes, and creating missing ones automatically. Delegates triple creation to ``execute_template()``. The old ``!triple add --template`` flag has been removed in favour of this command.
- **`!node add` command tree** — reorganised into groups:
  - `!node add concept` — generic entity with arc shortcuts (`--type`, `--superclass`, `--disjoint`). ``--inverse`` was removed (it is a predicate property, use ``!predicate add --inverse`` instead).
  - `!node add attachment photo|video|file|code` — file-attachment types with auto-created triples (was at the flat ``!node add photo|...`` before the reorganisation).
  - `!node add media book|film|song|game|podcast` — creative works with metadata triples, no file attachments.
  - `!node add scholarly paper|patent|conference` — academic/IP works with metadata triples, no file attachments.
- **Inline code support** (`node.add.attachment.code`): The ``--code`` flag accepts inline source code text, stored directly in the DB ``code_content`` column (FTS5-searchable). ``--path`` is optional (``group: "source"`` toggle in the GUI). ``--no-copy`` is removed for the code subcommand.
- **Language autocomplete**: The ``--lang`` flag supports a ``suggestions`` field with common programming languages rendered as a ``<datalist>`` in the GUI form.
- **Media/Scholarly helpers**: ``create_typed_node()`` and ``split_literals()`` in ``node_helpers.py`` provide shared node-creation and string-splitting utilities for the non-attachment typed subcommands.
- **Duration parsing**: ``parse_duration()`` in ``node_helpers.py`` converts ``HH:MM:SS`` to total seconds (string). Accepts ``HH:MM:SS``, ``MM:SS``, or plain integer.
- **Built-in predicates (sm: namespace)**: Defined in `graph/builtin_seed_data.py` and lazy-seeded by `graph/builtin_type_service.py`. Idempotent — safe to call on every startup.
- **Interactive commands**: Commands with `interactive: true` in `tree.py` trigger a form popup in the GUI when required params are missing.
  - **Field placeholders**: All ``add`` commands now include ``placeholder`` text in param/flag metadata showing example input (e.g. ``"en::physicist, eo::fizikisto, fr::physicien"`` for labels on concept).
  - **Group toggles**: Flags with a shared ``group`` key (e.g. ``"group": "source"``) are rendered as a mutually exclusive toggle in the GUI form. Only the active member's field is shown.
  - **Suggestions/datalist**: Flags with a ``suggestions`` list (e.g. programming languages for ``--lang``) are rendered as an ``<input>`` + ``<datalist>`` for autocomplete.
  - **Code type**: ``"type": "code"`` renders a multi-line ``<textarea>`` in the GUI form, paired with a Preview button.
- **LLM integration**: The chat endpoint can call graph query methods. Keep LLM calls async with timeout. The provider at `server/llm/provider.py` extends `lightercore.llm.BaseLLMProvider` and delegates config/profile persistence to `lightercore.llm` modules.
- **LLM chat flow (multi-round tool-calling)**:
  1. `POST /api/v1/llm/chat` — user sends NL message; backend runs `run_tool_loop` which calls `provider.chat_with_tools` with registered tool definitions
  2. LLM can call multiple tools per round — READ-level tools execute immediately, WRITE/DESTRUCTIVE tools gate behind user confirmation
  3. If write tools are present, the endpoint returns `{"type": "confirm_tool", "session_id": "...", "batch": [...], "message": "..."}` instead of a final reply
  4. Frontend shows a confirmation dialog with the batch of pending operations
  5. Frontend calls `POST /api/v1/llm/chat/resume` with `{session_id, decisions}` (or `confirmed: bool`) to approve or reject
  6. Resume continues the tool loop: approved tools execute, rejected tools are recorded as user rejection; LLM may call more tools or produce a final text answer
- **Same flow for prompt commands**: `/api/v1/prompt-commands/execute` returns `confirm_tool` for write tools; resume via `/api/v1/prompt-commands/execute/resume`
- **Legacy single-command confirm**: `POST /api/v1/llm/confirm` still available for the old flow (`{"type": "confirm", ...}` from the deprecated `generate_command` path). Both the backend and frontend support both formats.
- **User hooks directory**: ``~/.config/semantika/hooks/*.py`` — every ``.py`` file in this directory is loaded at startup (after system commands register). Each file executes in a pre-populated namespace so no imports are needed — ``command``, ``group_command``, ``call_system_command``, ``PermissionLevel``, ``CommandError``, ``CommandValidationError``, ``dispatch``, and ``get_services`` are automatically available. Files are loaded alphabetically; ``__init__.py``, hidden files, and editor backups are skipped. One bad file does not block others. Overridden commands can delegate to the original via ``call_system_command()``. See ``registry.py:freeze_system_commands`` / ``call_system_command`` / ``load_user_hooks`` / ``_build_hook_namespace``.
- **Permission gate**: The LLM chat route checks command `permission_level` before dispatch. Commands with level >= WRITE return `{"type": "confirm_tool", ...}` (batch) instead of executing immediately. Permission levels come from `@command(permission_level=...)` metadata; unset defaults to `WRITE`.
- **LLM provider architecture**: Uses `lightercore.llm` for ProviderConfig, keyring persistence, ProfileManager, and shared chat/command-generation infrastructure. The `LLMProvider` class is a singleton managed by `get_provider()` / `reset_provider()` — always use these instead of `LLMProvider()` directly.
- **Prompt command files**: Live at `~/.config/semantika/commands/*.md`. First line must start with `# ` (description). Positional args: `$1`, `$2`, …, `$9` and `$ARGUMENTS` catch-all. Parsed by `lightercore.prompt_commands`.
- **User config**: Persisted as JSON at `~/.local/share/semantika/user_config.json`. Atomic writes via temp+rename pattern. Supports `locale` (string), ``normalise_node_ids`` (bool), ``strip_diacritics_from_predicate_ids`` (bool). Boolean helpers: ``get_bool(key, default)``, ``set_bool(key, value)``.
- **When adding new routes**, always add corresponding `!command` entries via `@command()` decorator in `handlers/`
