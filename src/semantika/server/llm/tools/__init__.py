"""Semantika LLM tools — dedicated AI-optimised tool handlers.

Tools call graph services directly (no CLI pipeline) and use the
shared infrastructure from :mod:`lightercore.llm.tools`.

The core decorator, registry, and dispatch live in lightercore.
This module re-exports them and imports the domain-specific tool
modules to trigger ``@llm_tool`` registration.

Usage::

    from semantika.server.llm.tools import get_llm_tools

    tools = get_llm_tools()  # OpenAI-compatible tool definitions
"""

from lighterllm.llm.tools import (  # noqa: F401
    _llm_registry,
    dispatch_llm_tool,
    get_llm_tool_level,
    get_llm_tool_metadata,
    get_llm_tool_names,
    get_llm_tools,
    is_llm_tool,
    llm_tool,
)

# Import domain tool modules to trigger @llm_tool registration
from semantika.server.llm.tools import (  # noqa: F401
    graph,
    node,
    predicate,
    triple,
    template,
    search,
    sparql,
    system,
    review,
    unit,
)

__all__ = [
    "_llm_registry",
    "dispatch_llm_tool",
    "get_llm_tool_level",
    "get_llm_tool_metadata",
    "get_llm_tool_names",
    "get_llm_tools",
    "is_llm_tool",
    "llm_tool",
]
