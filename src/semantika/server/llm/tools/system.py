"""Semantika's system.now tool — re-exported from lightercore.

The canonical implementation lives in :mod:`lightercore.llm.tools.system`.
This module re-exports the handler and calls ``@llm_tool`` as a plain
function so that importing (or reloading) this module always triggers
registration in the shared registry — regardless of module caching.
"""

from lightercore.permissions import PermissionLevel
from lighterllm.llm.tools import llm_tool
from lighterllm.llm.tools.system import llm_system_now

# Re-register at module level so import always triggers the @llm_tool
# decorator.  Calling llm_tool(...) as a plain function (not a decorator)
# works because the decorator factory returns a callable that registers.
llm_tool(
    name="system.now",
    description=(
        "Get the current date and time in UTC and the local timezone. "
        "Use this for any temporal reasoning — determining what 'today' "
        "means, filtering by date, scheduling, or interpreting relative "
        "time references from the user."
    ),
    permission_level=PermissionLevel.READ,
)(llm_system_now)
