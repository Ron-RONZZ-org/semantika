"""Side-effect imports: registers all command handlers via @command decorators."""

from __future__ import annotations

from . import graph  # noqa: F401 — graph stats, export, import, search, view
from . import node  # noqa: F401 — node CRUD + node trash
from . import predicate  # noqa: F401 — predicate CRUD
from . import predicate_group  # noqa: F401 — predicate group CRUD
from . import triple  # noqa: F401 — triple CRUD + triple search
from . import unit  # noqa: F401
from . import trash  # noqa: F401 — node trash commands (node.trash.*)
from . import review  # noqa: F401
from . import llm  # noqa: F401
from . import backup  # noqa: F401
from . import reset  # noqa: F401
from . import user_config  # noqa: F401 — user config (!user config)
from . import predicate_trash  # noqa: F401 — predicate trash commands (predicate.trash.*)
