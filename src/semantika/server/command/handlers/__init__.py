"""Side-effect imports: registers all command handlers via @command decorators."""

from __future__ import annotations

from . import (
    backup,  # noqa: F401
    builtins,  # noqa: F401 — builtins reload
    context,  # noqa: F401 — context store for multi-turn flows
    graph,  # noqa: F401 — graph stats, export, import, search, view
    system,  # noqa: F401 — system.reindex
    help,  # noqa: F401 — !help command reference
    llm,  # noqa: F401
    node,  # noqa: F401 — node CRUD + node trash
    node_attachment,  # noqa: F401 — !node add attachment photo|video|file|code
    node_media,  # noqa: F401 — !node add media book|film|song|game|podcast
    node_scholarly,  # noqa: F401 — !node add scholarly paper|patent|conference
    predicate,  # noqa: F401 — predicate CRUD
    predicate_group,  # noqa: F401 — predicate group CRUD
    predicate_trash,  # noqa: F401 — predicate trash commands (predicate.trash.*)
    reset,  # noqa: F401
    review,  # noqa: F401
    sparql,  # noqa: F401 — SPARQL query commands
    template,  # noqa: F401 — triple template management (LLM tool use)
    trash,  # noqa: F401 — node trash commands (node.trash.*)
    triple,  # noqa: F401 — triple CRUD + triple search
    unit,  # noqa: F401
    user_config,  # noqa: F401 — user config (!user config)
)
