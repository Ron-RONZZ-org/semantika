"""Co-writing API route.

``POST /api/v1/cowrite`` — Send form content to LLM for editing.

Returns structured diffs (computed via ``difflib`` on the full revised
text returned by the LLM), along with the raw revised text for each
field.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from lightercore.cowrite.engine import cowrite as cowrite_engine
from lightercore.cowrite.style import load_cowrite_style
from lightercore.paths import config_dir
from semantika.core.cowrite_defaults import (
    DEFAULT_COWRITE_STYLE,
    DEFAULT_COWRITE_STYLE_NODE,
    DEFAULT_COWRITE_STYLE_PREDICATE,
    DEFAULT_COWRITE_STYLE_PROOF,
    DEFAULT_COWRITE_STYLE_REVIEW,
    DEFAULT_COWRITE_STYLE_TRIPLE,
    DEFAULT_COWRITE_STYLE_UNIT,
    _FORM_TYPE_TO_DOMAIN,
)
from semantika.server.llm.provider import get_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cowrite"])

_COWRITE_STYLE_DEFAULTS: dict[str, str] = {
    "general": DEFAULT_COWRITE_STYLE,
    "node": DEFAULT_COWRITE_STYLE_NODE,
    "predicate": DEFAULT_COWRITE_STYLE_PREDICATE,
    "triple": DEFAULT_COWRITE_STYLE_TRIPLE,
    "unit": DEFAULT_COWRITE_STYLE_UNIT,
    "review": DEFAULT_COWRITE_STYLE_REVIEW,
    "proof": DEFAULT_COWRITE_STYLE_PROOF,
}


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

    # Load cowrite style (general + per-domain cascade)
    style_content = load_cowrite_style(
        config_dir=config_dir(),
        form_type=form_type,
        form_type_to_domain=_FORM_TYPE_TO_DOMAIN,
        defaults=_COWRITE_STYLE_DEFAULTS,
    )

    try:
        result = await cowrite_engine(
            form_type=form_type,
            fields=fields,
            instruction=instruction,
            chat_fn=provider.chat,
            style_content=style_content,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result
