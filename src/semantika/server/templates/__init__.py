"""Triple template system — user-defined reusable semantic templates.

Templates live as YAML files in ``~/.config/semantika/templates/`` and
can be invoked via ``!triple add --template <name>``.

Public API:
    - :func:`loader.list_templates` — scan available templates
    - :func:`loader.load_template` — load a single template by name
    - :func:`executor.expand_template` — expand template into triple dicts
    - :func:`executor.execute_template` — expand and persist triples
"""

from semantika.server.templates.executor import execute_template, expand_template
from semantika.server.templates.loader import list_templates, load_template
from semantika.server.templates.models import TemplateParam, TriplePattern, TripleTemplate

__all__ = [
    "TemplateParam",
    "TriplePattern",
    "TripleTemplate",
    "execute_template",
    "expand_template",
    "list_templates",
    "load_template",
]
