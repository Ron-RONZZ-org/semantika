"""LLM tools for review session operations.

Provides review session status queries.
"""

from __future__ import annotations

import logging

from lightercore.permissions import PermissionLevel

from semantika.graph.db import get_services
from semantika.server.llm.tools import llm_tool

logger = logging.getLogger(__name__)


@llm_tool(
    name="review.status",
    description="Check if there is an active review session and get its "
    "details: progress (correct/total), creation date, and "
    "completion status.",
    permission_level=PermissionLevel.READ,
)
def llm_review_status(**kwargs) -> dict:
    """Get the status of any active review session."""
    svc = get_services()
    review_svc = svc.get("review")
    if not review_svc:
        return {"success": False, "error": "Review service not available"}

    try:
        session = review_svc.get_active_session() if hasattr(review_svc, "get_active_session") else None
        if session:
            return {
                "success": True,
                "data": {
                    "active": True,
                    "uuid": session.get("uuid", ""),
                    "mode": session.get("mode", ""),
                    "total": session.get("total", 0),
                    "correct": session.get("correct", 0),
                    "finished": bool(session.get("finished", 0)),
                    "created_at": session.get("created_at", ""),
                },
            }
        return {
            "success": True,
            "data": {"active": False},
        }
    except Exception as exc:
        logger.exception("review.status failed")
        return {"success": False, "error": str(exc)}
