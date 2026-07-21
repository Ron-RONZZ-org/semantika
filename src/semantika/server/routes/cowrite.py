"""Co-writing API route.

``POST /api/v1/cowrite`` — Send form content to LLM for editing.

Returns structured diffs (computed via ``difflib`` on the full revised
text returned by the LLM), along with the raw revised text for each
field.

User style is loaded from ``AGENTS.md`` (via :func:`load_user_style`),
which is shared with the main LLM system prompt — one file for all
style customisation.  The old per-domain ``cowrite_style*.md`` files
have been removed.

Response format is enforced at the API level by the engine itself
via ``response_format`` (JSON schema) when the provider supports it,
with graceful ``TypeError`` fallback to prompt-only enforcement.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from lighterllm.cowrite.engine import cowrite as cowrite_engine
from semantika.server.cowrite.context import gather_context
from semantika.server.llm.provider import get_provider
from semantika.server.llm.system_prompt import load_user_style

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cowrite"])


@router.post("/cowrite")
async def cowrite_endpoint(data: dict) -> dict:
    """Accept form content + instruction, return structured diffs.

    Request body:
        ``form_type`` (str): Type of form (``"node-add-concept"``,
            ``"triple-add"``, etc.).
        ``fields`` (dict): Current form content ``{field: text}``.
        ``instruction`` (str): User's editing instruction.

    Response:
        ``edits`` (dict): ``{field: [EditOp, ...]}``.
        ``revised`` (dict): ``{field: full_revised_text}``.
        ``original`` (dict): ``{field: original_text}``.
        ``session_id`` (str): Unique session identifier.
    """
    form_type = data.get("form_type", "").strip()
    fields = data.get("fields", {})
    instruction = data.get("instruction", "").strip()

    if not form_type:
        raise HTTPException(status_code=400, detail="form_type is required.")
    if not fields:
        raise HTTPException(status_code=400, detail="fields is required.")
    if not instruction:
        raise HTTPException(
            status_code=400,
            detail="instruction is required — tell the LLM what to do.",
        )

    # Validate that all field values are strings
    for key, val in fields.items():
        if not isinstance(val, str):
            raise HTTPException(
                status_code=400,
                detail=f"Field '{key}' must be a string.",
            )

    # Get the singleton LLM provider
    provider = get_provider()
    if not provider.available:
        raise HTTPException(
            status_code=502,
            detail="LLM not configured. Use ``!llm profile`` to set up a provider.",
        )

    # Load user style from AGENTS.md (shared with main LLM system prompt)
    style_content = load_user_style()

    # Gather writing samples context (RAG — recent samples only, no vector search yet)
    context = gather_context(form_type, fields)

    try:
        result = await cowrite_engine(
            form_type=form_type,
            fields=fields,
            instruction=instruction,
            chat_fn=provider.chat,
            style_content=style_content,
            context=context if context else None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result
