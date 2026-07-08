"""LLM integration routes — multi-round tool-calling chat with HITL.

``POST /api/v1/chat``        — Multi-round tool loop, replacing old one-shot flow.
``POST /api/v1/chat/resume`` — Resume paused HITL session.
``POST /api/v1/confirm``     — Legacy single-command confirmation (kept for compat).

The chat endpoint uses the shared :func:`run_tool_loop` from lightercore.
The LLM receives all registered ``!commands`` as native tools and can
call them, see results, and iterate until it produces a final answer.
WRITE-level tools gate behind user confirmation via ``/chat/resume``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from lightercore.llm.base import defs_to_tools
from lightercore.llm.tool_loop import resume_execution, run_tool_loop
from pydantic import BaseModel

from semantika.server.command.errors import CommandError
from semantika.server.command.registry import (
    dispatch,
    get_command_definitions,
    get_command_level,
    get_handler_metadata,
)
from semantika.server.llm.provider import get_provider

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


# ── Semantika system prompt ──────────────────────────────────────────────


_SEMANTIKA_SYSTEM_PROMPT = (
    "You are Semantika AI, the built-in assistant of the **Semantika "
    "knowledge graph** application. You run INSIDE the app and can "
    "call tools to create, read, and update graph data.\n\n"
    "## What Semantika Is\n"
    "Semantika stores structured knowledge as:\n"
    "- **Nodes** — entities or concepts (e.g. a book, a person, an idea)\n"
    "- **Predicates** — relationship types between nodes (e.g. author, theme)\n"
    "- **Triples** — subject-predicate-object statements\n\n"
    "## How to Use Tools\n"
    "- **Batch operations**: You can return MULTIPLE tool calls in a "
    "single response. If you need to create 3 nodes, call the add tool "
    "three times in one response — do NOT create them one at a time.\n"
    "- **Plan first**: Decide everything you need before calling tools, "
    "then batch all independent calls in a single round.\n"
    "- **Search before creating**: Always check if data already exists "
    "before creating duplicates (nodes, predicates).\n"
    "- **Prefer update over delete+recreate**: If something just needs "
    "changes, use the update tool instead of deleting and re-creating.\n"
    "- **Stop when done**: Once you have fetched or modified all the "
    "data the user asked for, produce a final text answer summarising "
    "what you did. Do NOT keep calling tools after the task is complete.\n\n"
    "## Write Operations\n"
    "Tools that modify data (add, update, delete, merge) will prompt "
    "the user for confirmation before executing. This is normal — "
    "explain what the tool will do when the confirmation dialog appears.\n\n"
    "## How to Respond\n"
    "- Keep responses concise and helpful. Use Markdown formatting.\n"
    "- Never invent data. If you truly have no data, say so clearly.\n"
    "- When you have completed the user's request, output a plain text "
    "answer summarising what you did. That signals the task is done."
)


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


@router.post("/profiles/{name}/load")
async def load_profile(name: str):
    """Load a saved profile by name."""
    provider = get_provider()
    config = provider.switch_to_profile(name)
    if config is None:
        raise HTTPException(404, f"Profile '{name}' not found")
    return {"status": "loaded", "profile": name}


# ── Chat ─────────────────────────────────────────────────────────────────


def _dispatch_path(path: str, flags: dict) -> dict:
    """Dispatch a command by dot-separated path."""
    return dispatch(path.split("."), flags)


@router.post("/chat")
async def chat(req: ChatRequest):
    """Chat with the LLM using multi-round tool-calling.

    Replaces the old one-shot ``generate_command`` → execute → summarise
    pipeline.  The LLM can now call tools, see results, and iterate
    until it produces a final answer.
    """
    if not req.message.strip():
        return {"reply": "Say something!"}

    provider = get_provider()
    if not provider.available:
        return {"reply": stub_response(req.message)["reply"]}

    # Build messages with system prompt + conversation history
    context = list(req.context or req.history or [])
    messages = [
        {"role": "system", "content": _SEMANTIKA_SYSTEM_PROMPT},
        *context,
        {"role": "user", "content": req.message},
    ]

    defs = get_command_definitions()
    tools = defs_to_tools(defs) if defs else []

    # Run the multi-round tool loop
    result = await run_tool_loop(
        messages=messages,
        tools=tools,
        name="chat",
        provider=provider,
        dispatch_fn=_dispatch_path,
        get_handler_metadata_fn=get_handler_metadata,
        get_command_level_fn=get_command_level,
    )

    # Handle confirm_tool pause
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    # Handle final text answer
    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        return {"reply": reply}

    # Tool loop produced nothing (error, empty response, or exhaustion).
    # Retry as a plain chat (no tool definitions) to distinguish between
    # an API error and the LLM simply declining to use tools.
    logger.warning("Tool loop returned empty for message=%r — retrying as plain chat", req.message)
    try:
        fallback = await provider.chat([
            {"role": "system", "content": _SEMANTIKA_SYSTEM_PROMPT},
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
            provider=provider,
            dispatch_fn=_dispatch_path,
            get_handler_metadata_fn=get_handler_metadata,
            get_command_level_fn=get_command_level,
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


def stub_response(message: str) -> dict:
    """Keyword-based stub responses when no LLM provider is configured."""
    msg = message.strip().lower()

    if "stats" in msg or "count" in msg or "how many" in msg:
        result = dispatch(["graph", "stats"], {})
        stats = result.get("data", {})
        return {
            "reply": (
                f"Your knowledge graph has **{stats.get('nodes', 0)}** nodes, "
                f"**{stats.get('predicates', 0)}** predicates, and "
                f"**{stats.get('triples', 0)}** triples."
            )
        }

    if "search" in msg or "find" in msg or "look for" in msg:
        for prefix in ["search for ", "search ", "find ", "look for "]:
            if prefix in msg:
                q = msg.split(prefix, 1)[1].strip()
                break
        else:
            q = message.strip()
        result = dispatch(["graph", "search"], {"q": q})
        data = result.get("data", {})
        nodes = data.get("nodes", [])
        if nodes:
            names = []
            for n in nodes[:5]:
                try:
                    labels = json.loads(n["labels"]) if isinstance(n["labels"], str) else n["labels"]
                    name = next(iter(labels.values())) if labels else n["node_id"]
                except (json.JSONDecodeError, TypeError, StopIteration):
                    name = n["node_id"]
                names.append(f"- **{name}** (`{n['node_id'][:12]}...`)")
            reply = f"I found {len(nodes)} matching nodes:\n" + "\n".join(names)
            if len(nodes) > 5:
                reply += f"\n…and {len(nodes) - 5} more."
            return {"reply": reply}
        return {"reply": f"I couldn't find anything matching '{q}'."}

    if msg.startswith("help") or msg.startswith("what can you"):
        return {
            "reply": (
                "I can help you explore your knowledge graph. Try:\n"
                "- **!ask** \"how many nodes do I have?\"\n"
                "- **!ask** \"search for something\"\n"
                "- **!ask** \"show me everything about X\"\n"
                "- Or type **!help** for all commands."
            )
        }

    # Greetings and introductions
    _greetings = {"hi", "hello", "hey", "greetings", "howdy",
                  "good morning", "good afternoon", "good evening", "good day"}
    if any(msg.startswith(g) for g in _greetings) or "who are you" in msg or "what are you" in msg:
        return {
            "reply": (
                "Hi! I'm **Semantika AI**, your knowledge graph assistant. "
                "I can help you build and explore structured knowledge as "
                "**nodes** (concepts), **predicates** (relationships), and "
                "**triples** (statements).\n\n"
                "I'm not connected to an LLM provider yet, so I can only "
                "respond to specific keywords. Here's what I can do:\n"
                "- Ask about **stats** \u2014 \"how many nodes do I have?\"\n"
                "- **Search** \u2014 \"find something\"\n"
                "- **!help** \u2014 see all available commands\n"
                "- **!llm configure** \u2014 connect an AI provider for full conversational chat"
            )
        }

    return {
        "reply": (
            "I can help you explore your knowledge graph. "
            "Try **stats**, **search**, or **!help** to get started, "
            "or run **!llm configure** to connect an AI provider for full conversational chat."
        )
    }
