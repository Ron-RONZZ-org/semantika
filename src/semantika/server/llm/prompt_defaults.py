"""Centralized shipped defaults for all Semantika prompt files.

Every prompt file that Semantika ships has its default content defined here.
This module is the single source of truth used by:

- ``dev_cli._seed_prompt_commands()`` — seeds the files on ``--seed``.
- ``prompt_commands_helpers.execute_template_flow()`` — inline fallbacks.
- ``PromptFilesManager`` — loaded at startup to enable ``!llm prompt list``
  and ``!llm prompt reset``.
- ``GET /api/v1/llm/prompts/list`` — provides default_content for the
  frontend's diff detection.
"""

from __future__ import annotations

from lightercore.prompt_files import PromptFile

# ── System prompts ───────────────────────────────────────────────────────────

DEFAULT_SEMANTIKA_PROMPT = (
    "You are Semantika AI, the built-in assistant of the **Semantika "
    "knowledge graph** application. You run INSIDE the app and can "
    "call tools to create, read, and update graph data.\n\n"
    "## What Semantika Is\n"
    "Semantika stores structured knowledge as:\n"
    "- **Nodes** — entities or concepts (e.g. a book, a person, an idea)\n"
    "- **Predicates** — relationship types between nodes (e.g. author, theme)\n"
    "- **Triples** — subject-predicate-object statements\n\n"
    "## How to Use Tools\n"
    "- **Batch operations**: You can return MULTIPLE tool calls in a "
    "single response. If you need to create 3 nodes, call the add tool "
    "three times in one response — do NOT create them one at a time.\n"
    "- **Plan first**: Decide everything you need before calling tools, "
    "then batch all independent calls in a single round.\n"
    "- **Search before creating**: Always check if data already exists "
    "before creating duplicates (nodes, predicates).\n"
    "- **Prefer update over delete+recreate**: If something just needs "
    "changes, use the update tool instead of deleting and re-creating.\n"
    "- **Stop when done**: Once you have fetched or modified all the "
    "data the user asked for, produce a final text answer summarising "
    "what you did. Do NOT keep calling tools after the task is complete.\n\n"
    "## Write Operations\n"
    "Tools that modify data (add, update, delete, merge) will prompt "
    "the user for confirmation before executing. This is normal — "
    "explain what the tool will do when the confirmation dialog appears.\n\n"
    "## How to Respond\n"
    "- Keep responses concise and helpful. Use Markdown formatting.\n"
    "- Never invent data. If you truly have no data, say so clearly.\n"
    "- When you have completed the user's request, output a plain text "
    "answer summarising what you did. That signals the task is done."
)

DEFAULT_AGENTS_STYLE = (
    "# AGENTS.md — Additional context for Semantika AI\n\n"
    "This file is loaded automatically and appended to the system prompt "
    "for ALL interactions (chat and prompt commands).  Use it to add your "
    "personal naming conventions, style preferences, or workflow rules.\n\n"
    "## Example\n"
    "```\n"
    "When creating nodes:\n"
    "- Always provide labels in eo, fr, en\n"
    "- Node ID from Esperanto label, uppercased, ASCII-normalised\n"
    "- Predicate IDs: rs:xxx with Esperanto word\n"
    "```\n"
)

# ── Template turn prompts ────────────────────────────────────────────────────

DEFAULT_TURN1 = (
    "# turn1 — predicate discovery\n"
    "Your task is to find existing predicates in the Semantika "
    "knowledge graph that are relevant to the user's template "
    "description, and create any that are missing.\n\n"
    "User description:\n"
    "$ARGUMENTS\n\n"
    "## Steps\n"
    "1. Use **predicate.search** to find relevant predicates. "
    "Try different keyword variations to get broad coverage.\n"
    "2. If an important predicate does not exist, create it with "
    "**predicate.add**.  Follow the naming conventions from the "
    "user's AGENTS.md style file (e.g. ``rs:xxx`` prefixed IDs).\n"
    "3. Once you have a good set of predicates (both existing and "
    "newly created), provide a concise summary listing the "
    "predicate IDs you found or created.\n"
)

DEFAULT_TURN2 = (
    "# turn2 — YAML template generation\n"
    "Generate a YAML template definition matching the user's description "
    "using the predicates available, then save it with ``template.save``.\n\n"
    "## Template Schema\n"
    "```yaml\n"
    "name: <short-name>\n"
    "description: <short-description>\n"
    "params:\n"
    "  - name: <variable-name>\n"
    "    label: <human-label>\n"
    "    type: node | string | number\n"
    "    required: true\n"
    "triples:\n"
    '  - "{var1} {predicate1} {var2}"           # URI (node ref)\n'
    '  - "{var1} {predicate2} {var3} --str"     # string literal\n'
    '  - "{var1} {predicate3} {var4} --int"     # number literal\n'
    "```\n\n"
    "## Rules\n"
    "- Each triple is a **single string**: `{subject} rs:predicate {object}`\n"
    "- Do NOT use dict format (``subject: ..., predicate: ...``) — "
    "that format is invalid and will be rejected by ``template.save``\n"
    "- No flag = URI reference (object is another node)\n"
    "- `--str` = string literal, `--int` = number literal\n"
    "- Optional params: if not filled, the triple is auto-skipped\n"
    "- Use PREDICATE IDs that already exist in your graph\n\n"
    "## Available predicates\n"
    "$AVAILABLE_PREDICATES\n\n"
    "## User description\n"
    "$TEMPLATE_DESCRIPTION\n\n"
    "## Style example\n"
    "Below is an example of a user-created template for reference "
    "(follow the same YAML structure):\n"
    "```yaml\n"
    "$STYLE_EXAMPLE\n"
    "```\n\n"
    "## Instructions\n"
    "1. Generate the YAML template content.\n"
    "2. If any predicates are missing, create them first using "
    "**predicate.add** before generating the template.\n"
    "3. Call **template.save** with ``--yaml`` set to the full YAML "
    "content to persist it to disk.\n"
    "4. The user will be asked to confirm — explain what the template "
    "contains so they can make an informed decision.\n"
    "5. After the tool completes, summarise what was created.\n\n"
    "You may also call **template.list** to check existing templates "
    "or **template.view** to inspect a template's structure.\n"
)

# ── Registered file list (for PromptFilesManager) ────────────────────────────

SEMANTIKA_PROMPT_FILES = [
    PromptFile(
        name="system-prompt",
        relative_path="system_prompt.md",
        default_content=DEFAULT_SEMANTIKA_PROMPT,
        category="system",
    ),
    PromptFile(
        name="agents",
        relative_path="AGENTS.md",
        default_content=DEFAULT_AGENTS_STYLE,
        category="system",
    ),
    PromptFile(
        name="template/turn1",
        relative_path="commands/_template_turns/turn1.md",
        default_content=DEFAULT_TURN1,
        category="turn",
    ),
    PromptFile(
        name="template/turn2",
        relative_path="commands/_template_turns/turn2.md",
        default_content=DEFAULT_TURN2,
        category="turn",
    ),
]


def get_prompt_files_manager() -> PromptFilesManager:
    """Return a PromptFilesManager configured with Semantika's shipped defaults.

    Uses :func:`lightercore.paths.config_dir` to locate the config directory.
    """
    from pathlib import Path

    from lightercore.paths import config_dir

    from lightercore.prompt_files import PromptFilesManager

    return PromptFilesManager(Path(config_dir()), SEMANTIKA_PROMPT_FILES)
