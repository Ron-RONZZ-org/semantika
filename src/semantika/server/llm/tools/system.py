"""LLM tools for system-level operations.

Provides the LLM with temporal awareness (``system.now``) so it can
accurately answer "today", "this week", or date-relative questions.
"""

from __future__ import annotations

import datetime

from lightercore.permissions import PermissionLevel

from semantika.server.llm.tools import llm_tool


@llm_tool(
    name="system.now",
    description="Get the current date and time.  Use this for any question "
    "that needs to know 'today', 'this week', 'this month', "
    "or any date-relative reasoning.",
    permission_level=PermissionLevel.READ,
)
def llm_system_now(**kwargs) -> dict:
    """Return the current datetime as an ISO 8601 string."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "success": True,
        "data": {
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "weekday": now.strftime("%A"),
            "timezone": "UTC",
        },
    }
