"""LLM integration routes — chat with tool-calling, config management.

Port of lighterbird's two-phase chat flow:
1. Generate structured command from natural language
2. Check permission level — gate destructive commands behind user confirm
3. Execute command and return result
4. If no command matched, respond as plain chat
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from lightercore.permissions import PermissionLevel
from semantika.server.llm.provider import get_provider, reset_provider
from semantika.server.command.registry import get_command_definitions

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
    """User confirmation to execute a destructive LLM-generated command."""
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


@router.post("/profiles/{name}/load")
async def load_profile(name: str):
    """Load a saved profile by name."""
    provider = get_provider()
    config = provider.switch_to_profile(name)
    if config is None:
        raise HTTPException(404, f"Profile '{name}' not found")
    return {"status": "loaded", "profile": name}


# ── Chat route (with command generation) ─────────────────────────────────


@router.post("/chat")
async def chat(req: ChatRequest):
    """Chat with the LLM, which may query the graph or execute commands.

    Two-phase flow:
    1. Try to generate a structured command from the user's message
    2. If a command was generated, execute it and summarize the result
    3. Otherwise, respond as a plain chat
    """
    if not req.message.strip():
        return {"reply": "Say something!"}

    provider = get_provider()

    # Build context from history
    messages = list(req.context or req.history or [])

    # Helper: try provider chat, fall back to stub on any error/network issue
    async def _safe_chat(prompt_messages: list[dict]) -> str | None:
        if not provider.available:
            return None
        try:
            return await provider.chat(prompt_messages)
        except Exception:
            return None

    from semantika.server.command.registry import get_command_tree

    defs = get_command_definitions(get_command_tree())
    cmd = None
    try:
        cmd = await provider.generate_command(req.message, defs)
    except Exception:
        cmd = None

    if cmd and cmd.get("tokens"):
        # Phase 2a: Permission check — gate destructive commands
        from semantika.server.command.registry import dispatch, get_command_level, get_handler_metadata
        from semantika.server.command.errors import CommandError

        cmd_path = ".".join(cmd["tokens"])
        level = get_command_level(cmd_path)
        if level >= PermissionLevel.DESTRUCTIVE:
            meta = get_handler_metadata(cmd_path)
            desc = meta.get("description", "") if meta else ""
            return {
                "type": "confirm",
                "tokens": cmd["tokens"],
                "flags": cmd.get("flags", {}),
                "message": (
                    f"The LLM wants to run a destructive command "
                    f"(`!{' '.join(cmd['tokens'])}`).\n\n"
                    f"{desc}\n\n"
                    "Confirm to proceed."
                ),
            }

        # Phase 2b: Execute the command
        try:
            result = dispatch(cmd["tokens"], cmd.get("flags", {}))
        except CommandError as e:
            # Command generation failed — try plain chat
            plain = await _safe_chat(messages + [{"role": "user", "content": req.message}])
            return {"reply": plain or _stub_response(req.message)["reply"]}

        # Phase 3: Summarize the result
        result_summary = json.dumps(result.get("data", result), indent=2, default=str)
        summary_messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant for the Semantika knowledge graph. "
                    "The user asked a question and the system executed a command on their behalf. "
                    "Summarize the result in a friendly, natural way. "
                    "Use markdown formatting for readability.\n\n"
                    "Command executed: !" + " ".join(cmd["tokens"]) + "\n"
                    "Result:\n" + result_summary
                ),
            },
            {"role": "user", "content": req.message},
        ]
        reply = await _safe_chat(summary_messages)
        if reply:
            return {"reply": reply}

    # Phase 3b: No command or summarization failed — plain chat or stub
    reply = await _safe_chat(messages + [{"role": "user", "content": req.message}])
    return {"reply": reply or _stub_response(req.message)["reply"]}


@router.post("/confirm")
async def confirm_command(req: ConfirmRequest) -> dict:
    """Execute a command after user confirmation.

    Called by the frontend after the user confirms a destructive
    LLM-generated command in the confirmation modal.  Dispatches
    directly without the permission gate — the user has approved it.
    """
    from semantika.server.command.errors import CommandError
    from semantika.server.command.registry import dispatch

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


# ── Stub fallback ────────────────────────────────────────────────────────


def _stub_response(message: str) -> dict:
    """Keyword-based stub responses when no LLM provider is configured."""
    msg = message.strip().lower()
    from semantika.graph.db import get_services

    if "stats" in msg or "count" in msg or "how many" in msg:
        stats = get_services()["triple"].get_stats()
        return {
            "reply": (
                f"Your knowledge graph has **{stats['nodes']}** nodes, "
                f"**{stats['predicates']}** predicates, and "
                f"**{stats['triples']}** triples."
            )
        }

    if "search" in msg or "find" in msg or "look for" in msg:
        for prefix in ["search for ", "search ", "find ", "look for "]:
            if prefix in msg:
                q = msg.split(prefix, 1)[1].strip()
                break
        else:
            q = message.strip()
        nodes = get_services()["node"].search(q)
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

    if "help" in msg or "what can you" in msg:
        return {
            "reply": (
                "I can help you explore your knowledge graph. Try:\n"
                "- **!ask** \"how many nodes do I have?\"\n"
                "- **!ask** \"search for something\"\n"
                "- **!ask** \"show me everything about X\"\n"
                "- Or type **!help** for all commands."
            )
        }

    return {
        "reply": (
            "I'm not connected to an LLM provider yet. "
            "Configure one via the LLM setup modal, or use !commands directly. "
            "Try keywords like \"stats\", \"search\", or \"help\"."
        )
    }
