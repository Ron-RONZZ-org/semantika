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
    "## Get predicate IDs from context\n"
    "Instead of relying on injected text, call **context.get(type=predicates)** "
    "to retrieve the exact predicate IDs discovered in the previous turn.\n\n"
    "## Template Schema\n"
    "```yaml\n"
    "name: <short-name>\n"
    "description: <short-description>\n"
    "params:\n"
    "  - name: <variable-name>\n"
    "    label: <human-label>\n"
    "    type: node | string | number\n"
    "    required: true\n"
    "    languages: [en, fr]       # optional — for node-type params\n"
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
    "- Use PREDICATE IDs only from **context.get**\n"
    "- For node-type params, use ``languages: [en, fr, ...]`` to hint at\n"
    "  the expected label languages (informational — shown in ``!template view``).\n\n"
    "## User description\n"
    "$TEMPLATE_DESCRIPTION\n\n"
    "## Style example\n"
    "Below is an example of a user-created template for reference "
    "(follow the same YAML structure):\n"
    "```yaml\n"
    "$STYLE_EXAMPLE\n"
    "```\n\n"
    "## Instructions\n"
    "1. Call **context.get(type=predicates)** to see available predicates.\n"
    "2. Generate the YAML template content using those predicate IDs.\n"
    "3. If any predicates are missing, create them first using "
    "**predicate.add** before generating the template.\n"
    "4. Call **template.save** with ``--yaml`` set to the full YAML "
    "content to persist it.\n"
    "5. The user will be asked to confirm — explain what the template "
    "contains so they can make an informed decision.\n"
    "6. After the tool completes, summarise what was created.\n\n"
    "You may also call **template.list** to check existing templates "
    "or **template.view** to inspect a template's structure.\n"
)


# ── Text-to-triples turn prompts ────────────────────────────────────────────

DEFAULT_TTT_TURN1 = (
    "# TTT turn1 — Node discovery\n"
    "Identify all entities mentioned in the user's text and create "
    "nodes for them in the knowledge graph.\n\n"
    "User text:\n"
    "$ARGUMENTS\n\n"
    "## Steps\n"
    "1. Identify every entity (person, book, concept, place, etc.) "
    "mentioned in the text.\n"
    "2. For each entity, use **node.search** to check if it already "
    "exists. Try different keyword variations and languages.\n"
    "3. For entities that do not exist, use **node.add** to create "
    "nodes with appropriate labels (English by default).\n"
    "4. Batch all searches first, then batch all creations in a "
    "single response.\n"
    "5. Once done, provide a summary listing all node IDs "
    "(both found and newly created).\n"
)

DEFAULT_TTT_TURN2 = (
    "# TTT turn2 — Template and predicate discovery\n"
    "Find matching triple templates and create any predicates "
    "needed for the user's text.\n\n"
    "User text:\n"
    "$ARGUMENTS\n\n"
    "## Steps\n"
    "1. Call **template.list** to check if any existing templates "
    "match the type of data in the text.\n"
    "2. If a template seems relevant, call **template.view** "
    "to inspect its structure.\n"
    "3. For each relationship in the text, use **predicate.search** "
    "to find existing predicates.\n"
    "4. If a needed predicate does not exist, create it with "
    "**predicate.add**.\n"
    "5. Once done, provide a summary of templates found and "
    "predicates discovered or created.\n"
)

DEFAULT_TTT_TURN3 = (
    "# TTT turn3 — Triple creation\n"
    "Create the actual triples from the text using the nodes "
    "and predicates discovered in previous turns.\n\n"
    "User text:\n"
    "$ARGUMENTS\n\n"
    "## CRITICAL: Get exact IDs from context\n"
    "Before creating any triples, call **context.get(type=all)** "
    "to retrieve the exact node and predicate IDs. Use ONLY those IDs.\n\n"
    "## Steps\n"
    "1. Call **context.get(type=all)** to see available nodes, "
    "predicates, and templates.\n"
    "2. If a matching template was found in the previous turn, "
    "use **!template use <name> --param1 <label> --param2 <label>** "
    "with labels (it will create missing nodes automatically).\n"
    "   For node params, you can provide labels in multiple languages:\n"
    "   - ``--param '{\"en\": \"Title\", \"fr\": \"Titre\"}'`` (JSON)\n"
    "   - ``--param \"en::Title, fr::Titre\"`` (LANG::TEXT)\n"
    "3. Otherwise, create triples directly with "
    "**!triple.add --subject_id <id> --predicate_id <id> --object_value <value>**.\n"
    "4. Use ``--str`` for string literals, ``--int`` for numbers, "
    "``--lang <code>`` for language tags.\n"
    "5. Batch all triples in a single response.\n"
    "6. After creating triples, summarise what was created.\n"
    "7. If the text contains a pattern that repeats, suggest creating "
    "a reusable template via **/template**.\n"
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
    # Text-to-triples turns
    PromptFile(
        name="text-to-triples/turn1",
        relative_path="commands/_text_to_triple_turns/turn1.md",
        default_content=DEFAULT_TTT_TURN1,
        category="turn",
    ),
    PromptFile(
        name="text-to-triples/turn2",
        relative_path="commands/_text_to_triple_turns/turn2.md",
        default_content=DEFAULT_TTT_TURN2,
        category="turn",
    ),
    PromptFile(
        name="text-to-triples/turn3",
        relative_path="commands/_text_to_triple_turns/turn3.md",
        default_content=DEFAULT_TTT_TURN3,
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
