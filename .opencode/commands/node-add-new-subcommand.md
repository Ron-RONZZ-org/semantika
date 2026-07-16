---
description: |
  Create a new specialised !node add subcommand (e.g. !node add media recipe).
  Provides everything an LLM needs: predicate registration, handler code, CLI/GUI wiring, tests.
agent: architect
---

# Adding a New `!node add X` Subcommand

This document is the canonical reference for implementing a new specialised
`!node add` subcommand in Semantika.  Follow it step by step.

---

## 1. Decide where it goes

The `!node add` command tree is:

```
!node add concept                   — generic entity (node.py)
!node add attachment photo|video|file|code  — file-attachment (node_attachment.py)
!node add media book|film|song|game|podcast — creative works (node_media.py)
!node add scholarly paper|patent|conference — academic/IP (node_scholarly.py)
```

| If your command is… | Put it in… |
|---------------------|------------|
| A file-attachment type | `node_attachment.py` |
| A creative work (pure metadata) | `node_media.py` |
| An academic/IP work (pure metadata) | `node_scholarly.py` |
| Something that fits none of the above | Create a new `node_*.py` in `handlers/` AND add its import to `__init__.py` |

---

## 2. Register new predicates (`sm:xxx`)

Add a tuple to `BUILTIN_PREDICATES` in `src/semantika/graph/builtin_seed_data.py`:

```python
(
    "sm:hasRecipe",
    "semantika",
    {"en": "recipe", "eo": "recepto", "fr": "recette"},
    {"en": "A recipe associated with a dish or food item", "eo": "Recepto asociita kun plado aŭ manĝaĵo"},
),
```

The handler calls `create_typed_node()` which runs `ensure_builtins()` internally,
so predicates from `BUILTIN_PREDICATES` are auto-seeded on first use.

**New type nodes** (if this introduces a new `rdf:type`):

Add to `BUILTIN_TYPE_NODES` in the same file:

```python
{
    "node_id": "RECIPE",
    "labels": {"en": "Recipe", "eo": "Recepto", "fr": "Recette"},
    "definitions": {"en": "A set of instructions for preparing a dish", ...},
},
```

---

## 3. Write the handler

### Pattern A — Pure metadata (no file attachment) — use `create_typed_node()`

Example from `node_media.py` (book):

```python
@command("node.add.media.book",
         description="Create a book node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "THE_GREAT_GATSBY"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::The Great Gatsby"},
             {"name": "isbn", "type": "string",
              "help": "ISBN(s) (comma-separated for multiple editions)",
              "placeholder": "9780743273565"},
             {"name": "author", "type": "string",
              "help": "Author node IDs (comma-separated)",
              "placeholder": "F_SCOTT_FITZGERALD"},
         ])
def cmd_node_add_book(remaining: list[str], flags: dict[str, str]) -> dict:
    """Docstring: describe what auto-created triples this command makes."""
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")

    # Resolve node refs from comma-separated values
    author_nodes = resolve_node_refs(svc, flags.get("author", "") or "", "author")

    # Split literal comma-separated values
    isbns = split_literals(flags.get("isbn", "") or "")

    extra_fields: list[tuple[str, str, str, str]] = []
    for isbn in isbns:
        extra_fields.append(("sm:hasISBN", isbn, "literal", ""))
    for author_id in author_nodes:
        extra_fields.append(("sm:hasAuthor", author_id, "uri", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "BOOK", extra_fields)
    return {"type": "status", "data": result}
```

Key imports:
```python
from semantika.graph.db import get_services
from semantika.server.command.handlers.node_helpers import (
    create_typed_node,
    parse_duration,
    resolve_node_refs,
    split_literals,
)
from semantika.server.command.registry import command
```

### Pattern B — File attachment — use `attach_file_and_create_node()`

See `node_attachment.py` for examples (photo, video, file, code).
Uses `attach_file_and_create_node()` instead of `create_typed_node()`.

### Pattern C — Inline-paste code — custom logic

See `cmd_node_add_code` + `_create_inline_code_node()` in `node_attachment.py`.

---

## 4. CLI/GUI wiring (auto — no manual steps needed)

The `@command()` decorator automatically:
- Registers the command in the dispatch table → **CLI works** immediately
- Adds it to the command tree (served via `GET /api/v1/command/tree`) → **autocomplete works**
- Generates tool definitions for LLM tool-calling → **LLM can invoke it**
- Sets `interactive=True` → **GUI form** is shown when required params are missing

The forward-end (Svelte) automatically renders forms based on the flag metadata
(`placeholder`, `suggestions`, `group`, `type: "code"`). No frontend code changes needed
for standard forms.

**Flag metadata tips:**

| Metadata | Effect |
|----------|--------|
| `"placeholder": "..."` | Example text shown in the input field |
| `"suggestions": ["a", "b"]` | Autocomplete dropdown (`<datalist>`) |
| `"group": "source"` | Mutually exclusive toggle — only one shown at a time |
| `"type": "code"` | Multi-line `<textarea>` with Preview (Ctrl+Shift+P) |
| `"required": True` | Field must be filled before form can submit |

---

## 5. Write tests

Create tests in `tests/test_server/`.  Follow the pattern from
`test_handler_node_add_media_scholarly.py`:

```python
"""Tests for node.add.media.<command>."""

import pytest
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.handlers import node_media  # noqa: F401
from semantika.server.command.registry import dispatch


@pytest.fixture
def seeded(services: dict) -> dict:
    """Create seed nodes for test dependencies."""
    ns = services["node"]
    ns.create({"node_id": "CHEF", "labels": {"en": "Famous Chef"}})
    return services


class TestNodeAddRecipe:
    def test_recipe_basic(self, seeded: dict):
        """Basic creation should work."""
        result = dispatch(
            ["node", "add", "media", "recipe"],
            {"labels": "en::Bouillabaisse"},
        )
        assert result["type"] == "status"
        assert result["data"]["node"] is not None

    def test_recipe_with_author(self, seeded: dict):
        """--author should create sm:hasAuthor triple."""
        result = dispatch(
            ["node", "add", "media", "recipe"],
            {"labels": "en::Bouillabaisse", "author": "CHEF"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasAuthor" for t in triples)

    def test_tree_has_recipe(self):
        """Verify subcommand appears in tree."""
        from semantika.server.command.registry import get_command_tree
        tree = get_command_tree()
        # Navigate to the appropriate group's children...
        add_entry = next(
            c for c in next(n for n in tree if n["name"] == "node")["children"]
            if c["name"] == "add"
        )
        media_entry = next(c for c in add_entry["children"] if c["name"] == "media")
        child_names = [c["name"] for c in media_entry.get("children", [])]
        assert "recipe" in child_names
```

---

## 6. Update documentation

- **Root AGENTS.md**: Update the command tree listing and "Node Handler Module Split" table
  if adding a new handler file.
- **server/AGENTS-server.md**: Update the specialised subcommands section if adding new
  predicates or type nodes to mention them.
- **Handler file docstring**: Update the module docstring to list the new command.

---

## Quick reference: `extra_fields` types

| Object type | When to use | Example |
|-------------|-------------|---------|
| `"uri"` | Value is a **node ID** (creates FK relationship) | `("sm:hasAuthor", author_id, "uri", "")` |
| `"literal"` | Value is a **plain string/number** | `("sm:hasISBN", isbn, "literal", "")` |
| `"literal"` + `"xsd:integer"` | Value is a number with a type hint | `("sm:publicationYear", year, "literal", "xsd:integer")` |

**Comma-separated values**: Always create one triple per value (never a single triple
with a comma-joined string).  This follows the RDF triple-store nature — each triple
is independently queryable via SPARQL.

---

## Quick reference: helper functions

| Function | Location | Purpose |
|----------|----------|---------|
| `create_typed_node()` | `node_helpers.py` | Create node + `rdf:type` + extra triples (no file) |
| `attach_file_and_create_node()` | `node_helpers.py` | Create node + file attachment + type + triples |
| `parse_dimension()` | `node_helpers.py` | Parse `1920x1080` → `"1920x1080"` |
| `parse_duration()` | `node_helpers.py` | Parse `02:30:00` → `"9000"` (seconds) |
| `resolve_node_refs()` | `node_helpers.py` | Resolve comma-separated node refs → list of node IDs |
| `split_literals()` | `node_helpers.py` | Split comma-separated string → list of tokens |
