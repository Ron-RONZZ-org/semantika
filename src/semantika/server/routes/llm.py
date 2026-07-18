"""LLM integration routes — multi-round tool-calling chat with HITL.

``POST /api/v1/chat``        — Multi-round tool loop using dedicated LLM tools.
``POST /api/v1/chat/resume`` — Resume paused HITL session.
``POST /api/v1/confirm``     — Legacy single-command confirmation (kept for compat).

The chat endpoint uses the shared :func:`run_tool_loop` from lightercore.
The LLM receives **dedicated AI-optimised tools** from
:mod:`~semantika.server.llm.tools` (not CLI command definitions) — these
call graph services directly with clean parameter schemas and return
structured data without frontend-shaped wrapping.  WRITE-level tools gate
behind user confirmation via ``/chat/resume``.

See :mod:`semantika.server.llm.tools` for the tool registry.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from lightercore.llm.tool_loop import resume_execution, run_tool_loop
from pydantic import BaseModel

from semantika.server.command.errors import CommandError
from semantika.server.command.registry import (
    dispatch,
    get_command_definitions,
    get_command_level,
    get_command_tree,
    get_handler_metadata,
)
from semantika.server.llm.provider import get_provider
from semantika.server.llm.system_prompt import load_system_prompt, reload_system_prompt, system_prompt_path
from semantika.server.llm.tools import (
    dispatch_llm_tool,
    get_llm_tool_level,
    get_llm_tool_metadata,
    get_llm_tools,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = ""
    history: list[dict] = []
    context: list[dict] = []


class ConfigureRequest(BaseModel):
    provider_type: str = "deepseek"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048


class ProfileSaveRequest(BaseModel):
    name: str
    provider_type: str = "deepseek"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048


class ConfirmRequest(BaseModel):
    """Legacy single-command confirmation."""
    tokens: list[str]
    flags: dict[str, str] = {}


# ── Config routes ────────────────────────────────────────────────────────


@router.get("/config")
async def llm_config():
    """Return whether an LLM provider is available."""
    provider = get_provider()
    return {"available": provider.available}


@router.post("/configure")
async def llm_configure(req: ConfigureRequest):
    """Save the active provider configuration to keyring."""
    provider = get_provider()
    cfg = provider.configure(
        provider_type=req.provider_type,
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    return {"status": "configured", "provider_type": cfg.provider_type, "model": cfg.model}


@router.get("/profiles")
async def list_profiles():
    """List saved LLM profiles (stored in keyring)."""
    provider = get_provider()
    return {"profiles": provider.list_profiles()}


@router.post("/profiles", status_code=201)
async def create_profile(req: ProfileSaveRequest):
    """Save a named LLM profile."""
    provider = get_provider()
    provider.save_profile(
        name=req.name,
        provider_type=req.provider_type,
        api_key=req.api_key,
        base_url=req.base_url,
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    return {"status": "created", "name": req.name}


@router.get("/profiles/{name}")
async def get_profile(name: str):
    """Return a single profile by name."""
    provider = get_provider()
    profiles = provider.list_profiles()
    for p in profiles:
        if p.get("name", "").lower() == name.lower():
            return p
    raise HTTPException(404, f"Profile '{name}' not found")


@router.patch("/profiles/{name}")
async def update_profile(name: str, req: ProfileSaveRequest):
    """Update a named LLM profile (partial)."""
    provider = get_provider()
    # Load existing config to preserve unchanging fields
    existing = provider.switch_to_profile(name)
    if existing is None:
        raise HTTPException(404, f"Profile '{name}' not found")

    # Switch back to active profile (switch_to_profile changes the active)
    from lightercore.llm.config import load_active_config
    from lightercore.llm.profiles import ProfileManager

    pm = ProfileManager("semantika-llm", provider._profile_dir)
    active = load_active_config("semantika-llm")
    if active and active.name:
        provider.switch_to_profile(active.name)

    provider.save_profile(
        name=name,
        provider_type=req.provider_type or existing.provider_type,
        api_key=req.api_key or existing.api_key or "",
        base_url=req.base_url or existing.base_url or "",
        model=req.model or existing.model or "",
        temperature=req.temperature or existing.temperature,
        max_tokens=req.max_tokens or existing.max_tokens,
    )
    return {"status": "updated", "name": name}


@router.delete("/profiles/{name}")
async def delete_profile(name: str):
    """Delete a saved LLM profile."""
    provider = get_provider()
    if not provider.delete_profile(name):
        raise HTTPException(404, f"Profile '{name}' not found")
    return {"status": "deleted", "name": name}


@router.post("/profiles/{name}/load")
async def load_profile(name: str):
    """Load a saved profile by name."""
    provider = get_provider()
    config = provider.switch_to_profile(name)
    if config is None:
        raise HTTPException(404, f"Profile '{name}' not found")
    return {"status": "loaded", "profile": name}


# ── System prompt endpoints ─────────────────────────────────────────────


@router.get("/prompt")
async def get_system_prompt() -> dict:
    """Return the current system prompt content and its file path.

    The user can edit the file at *path* to customise the LLM's
    behaviour, then call ``POST /api/v1/llm/reload-prompt`` to apply
    changes without restarting the server.
    """
    return {
        "prompt": load_system_prompt(),
        "path": str(system_prompt_path()),
    }


@router.post("/reload-prompt")
async def reload_system_prompt_endpoint() -> dict:
    """Force-reload the system prompt from disk.

    Call this after the user edits ``system_prompt.md`` so the LLM
    sees the new content on the next request (no server restart needed).
    """
    prompt = reload_system_prompt()
    return {
        "status": "reloaded",
        "length": len(prompt),
        "path": str(system_prompt_path()),
    }


# ── Chat ─────────────────────────────────────────────────────────────────


def _get_combined_metadata(path: str) -> dict | None:
    """Combined metadata lookup: LLM tool registry first, then CLI registry.

    The LLM tool registry stores ``description`` in its entries, which
    :func:`~lightercore.llm.tool_loop.run_tool_loop` uses to populate
    the ``confirm_tool`` dialog descriptions.
    """
    meta = get_llm_tool_metadata(path)
    if meta:
        return meta
    return get_handler_metadata(path)


@router.post("/chat")
async def chat(req: ChatRequest):
    """Chat with the LLM using multi-round tool-calling.

    The LLM receives **dedicated AI-optimised tools** (not CLI command
    definitions) that call graph services directly.  WRITE-level tools
    gate behind user confirmation via ``/chat/resume``.
    """
    if not req.message.strip():
        return {"reply": "Say something!"}

    provider = get_provider()
    if not provider.available:
        return {"reply": stub_response(req.message)["reply"]}

    # Build messages with system prompt + conversation history
    context = list(req.context or req.history or [])
    messages = [
        {"role": "system", "content": load_system_prompt()},
        *context,
        {"role": "user", "content": req.message},
    ]

    # Use dedicated LLM tools (not CLI command definitions)
    tools = get_llm_tools()

    # Run the multi-round tool loop
    result = await run_tool_loop(
        messages=messages,
        tools=tools,
        name="chat",
        provider=provider,
        dispatch_fn=dispatch_llm_tool,
        get_handler_metadata_fn=_get_combined_metadata,
        get_command_level_fn=get_command_level,
        get_tool_level_fn=get_llm_tool_level,
    )

    # Handle confirm_tool pause
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    # Handle final text answer
    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        return {"reply": reply}

    # Tool loop produced nothing — retry as plain chat
    logger.warning("Tool loop returned empty for message=%r — retrying as plain chat", req.message)
    try:
        fallback = await provider.chat([
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": req.message},
        ])
        if isinstance(fallback, str) and fallback.strip():
            return {"reply": fallback}
    except Exception as exc:
        logger.error("Plain chat fallback also failed: %s", exc)
        return {"reply": f"I'm having trouble reaching the LLM provider: {exc}"}

    # Both paths failed — unlikely, but be friendly
    return {"reply": "I wasn't able to process that right now. Try using !help to see available commands."}


@router.post("/chat/resume")
async def chat_resume(data: dict) -> dict:
    """Resume a paused chat execution after user confirmation.

    Request body:
        session_id (str): Session UUID from ``confirm_tool`` response.
        decisions (dict[int, bool], optional): Per-tool-index approval.
        confirmed (bool, optional): Blanket approve/reject all tools.
        feedback (dict[int, str] | str, optional): User feedback for
            rejected tools. A dict maps tool index to feedback string;
            a string is applied to all rejected tools.
    """
    session_id = data.get("session_id", "")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required.")

    provider = get_provider()
    if not provider.available:
        return {"reply": "LLM not configured."}

    try:
        result = await resume_execution(
            session_id=session_id,
            decisions=data.get("decisions"),
            confirmed=data.get("confirmed"),
            feedback=data.get("feedback"),
            provider=provider,
            dispatch_fn=dispatch_llm_tool,
            get_handler_metadata_fn=_get_combined_metadata,
            get_command_level_fn=get_command_level,
            get_tool_level_fn=get_llm_tool_level,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        return {"reply": reply}

    return {"reply": "(command completed)"}


# ── Legacy confirm (kept for backward compat) ────────────────────────────


@router.post("/confirm")
async def confirm_command(req: ConfirmRequest) -> dict:
    """Execute a command after user confirmation (legacy).

    Called by any existing frontend code that still uses the old
    single-command confirmation flow.
    """
    if not req.tokens:
        raise HTTPException(status_code=400, detail="No command tokens provided.")

    try:
        result = dispatch(req.tokens, req.flags)
    except CommandError as e:
        raise HTTPException(status_code=400, detail={
            "error": str(e), "suggestion": getattr(e, "suggestion", "")})

    return {
        "type": result.get("type", "status"),
        "title": result.get("title", ""),
        "data": result.get("data", result),
    }


# ── Stub fallback (when no LLM configured) ───────────────────────────────


_GREETINGS = {
    "hi", "hello", "hey", "greetings", "howdy",
    "good morning", "good afternoon", "good evening", "good day",
}


def _greeting_response() -> dict:
    """Return a friendly greeting with setup instructions."""
    return {
        "reply": (
            "Hi! I'm **Semantika AI**, your knowledge graph assistant. "
            "I help you build and explore structured knowledge as "
            "**nodes** (concepts), **predicates** (relationships), and "
            "**triples** (statements).\n\n"
            "I'm not connected to an LLM provider yet. "
            "Run **!llm configure** to connect an AI provider, "
            "or type **!help** to see all available commands."
        )
    }


def _help_response() -> dict:
    """Return a help-oriented response."""
    return {
        "reply": (
            "I can help you explore your knowledge graph. Try:\n"
            "- **!ask** \"how many nodes do I have?\"\n"
            "- **!ask** \"search for something\"\n"
            "- **!ask** \"show me everything about X\"\n"
            "- Or type **!help** for all commands."
        )
    }


def _command_category_hint() -> str:
    """Build a hint string from the current command tree top-level entries."""
    try:
        tree = get_command_tree()
        names = [n["name"] for n in tree if n.get("description") and n.get("children")]
        if names:
            return ", ".join(names[:8])
    except Exception:
        pass
    return "node, predicate, triple, graph"


def stub_response(message: str) -> dict:
    """Stub response when no LLM provider is configured.

    Uses the live command tree to provide relevant hints, so the
    response stays in sync as commands are added or removed.
    """
    msg = message.strip().lower()

    # Greetings
    if any(msg.startswith(g) for g in _GREETINGS) or "who are you" in msg or "what are you" in msg:
        return _greeting_response()

    # Help / what-can-you-do
    if msg.startswith("help") or msg.startswith("what can you"):
        return _help_response()

    # Fallback: show available command categories
    categories = _command_category_hint()
    return {
        "reply": (
            f"I'm not connected to an LLM provider, so I can't answer "
            f"freely. Available command areas: **{categories}**.\n\n"
            f"Run **!llm configure** to connect an AI provider, "
            f"or **!help** for all commands."
        )
    }
