"""Co-writing API route.

``POST /api/v1/cowrite`` — Send form content to LLM for editing.

Returns structured diffs (computed via ``difflib`` on the full revised
text returned by the LLM), along with the raw revised text for each
field.

User style is loaded from ``AGENTS.md`` (via :func:`load_user_style`),
which is shared with the main LLM system prompt — one file for all
style customisation.  The old per-domain ``cowrite_style*.md`` files
have been removed.

Response format is enforced at the API level via ``response_format``
(JSON schema) when the provider supports it, with graceful fallback
to prompt-only enforcement otherwise.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException

from lightercore.cowrite.engine import cowrite as cowrite_engine
from semantika.server.cowrite.context import gather_context
from semantika.server.llm.provider import get_provider
from semantika.server.llm.system_prompt import load_user_style

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cowrite"])


def _build_json_schema(fields: dict[str, str]) -> dict:
    """Build an OpenAI-compatible ``json_schema`` response_format for cowrite.

    The schema ensures the LLM returns ONLY the requested fields, each as a
    string, with no extra keys — enforced at the API level when the provider
    supports structured output.
    """
    properties = {name: {"type": "string"} for name in fields}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "cowrite_response",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(fields.keys()),
                "additionalProperties": False,
            },
        },
    }


async def _cowrite_chat_with_schema(
    chat_fn: callable,
    messages: list[dict],
    fields: dict[str, str],
) -> str:
    """Call *chat_fn* with API-level schema enforcement, falling back gracefully.

    Tier 1 — strict JSON schema (OpenAI, compatible providers).
    Tier 2 — weak JSON object mode (DeepSeek, some compat APIs).
    Tier 3 — prompt-only (Ollama, everything else; uses
             ``_clean_llm_response`` in the engine for parsing).
    """
    strict_schema = _build_json_schema(fields)

    # Tier 1: strict schema
    try:
        return await chat_fn(messages, response_format=strict_schema)
    except Exception:
        logger.debug("Strict JSON schema not supported, falling back to json_object")
        pass

    # Tier 2: weak JSON guarantee
    try:
        return await chat_fn(
            messages, response_format={"type": "json_object"},
        )
    except Exception:
        logger.debug("json_object not supported either, falling back to prompt-only")
        pass

    # Tier 3: prompt-only (works everywhere)
    return await chat_fn(messages)


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

    # Wrap provider.chat with JSON schema enforcement + fallback
    async def cowrite_chat(messages: list[dict], **kwargs: object) -> str:
        return await _cowrite_chat_with_schema(provider.chat, messages, fields)

    # Gather writing samples context (RAG — recent samples only, no vector search yet)
    context = gather_context(form_type, fields)

    try:
        result = await cowrite_engine(
            form_type=form_type,
            fields=fields,
            instruction=instruction,
            chat_fn=cowrite_chat,
            style_content=style_content,
            context=context if context else None,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result
