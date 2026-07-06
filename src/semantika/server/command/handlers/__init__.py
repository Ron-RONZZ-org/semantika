"""Side-effect imports: registers all command handlers via @command decorators."""

from __future__ import annotations

from . import (
    backup,  # noqa: F401
    graph,  # noqa: F401 — graph stats, export, import, search, view
    llm,  # noqa: F401
    node,  # noqa: F401 — node CRUD + node trash
    predicate,  # noqa: F401 — predicate CRUD
    predicate_group,  # noqa: F401 — predicate group CRUD
    predicate_trash,  # noqa: F401 — predicate trash commands (predicate.trash.*)
    reset,  # noqa: F401
    review,  # noqa: F401
    trash,  # noqa: F401 — node trash commands (node.trash.*)
    triple,  # noqa: F401 — triple CRUD + triple search
    unit,  # noqa: F401
    user_config,  # noqa: F401 — user config (!user config)
)
