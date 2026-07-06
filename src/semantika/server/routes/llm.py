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

from fastapi import APIRouter, HTTPException
from lightercore.permissions import PermissionLevel
from pydantic import BaseModel

from semantika.server.command.registry import (
    get_command_definitions,
    get_command_tree,
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

    from semantika.server.command.errors import CommandError
    from semantika.server.command.registry import (
        dispatch,
        get_command_level,
        get_handler_metadata,
    )

    # ── Helper: detect write/modify commands ─────────────────────────────
    _WRITE_VERBS = {
        "add", "new", "delete", "remove", "update", "set", "modify",
        "edit", "rename", "merge", "clear", "purge", "restore",
        "import", "prune", "load", "save", "create",
    }

    def _is_write_command(tokens: list[str]) -> bool:
        """Return ``True`` if *tokens* describe a data-modifying action."""
        if not tokens:
            return False
        leaf = tokens[-1].lower()
        return leaf in _WRITE_VERBS

    # ── Helper: try to execute a command and return the result dict ──────
    async def _try_execute(
        tokens: list[str],
        flags: dict[str, str],
    ) -> dict | None:
        """Attempt to dispatch *tokens*.  Returns the result dict on success
        or ``None`` if the command path doesn't exist."""
        try:
            return dispatch(tokens, flags)
        except CommandError:
            return None

    # ── Helper: summarise command output ─────────────────────────────────
    async def _summarise(
        tokens: list[str],
        result: dict,
        user_message: str,
    ) -> str | None:
        """Ask the LLM to summarise a command execution result."""
        result_summary = json.dumps(
            result.get("data", result), indent=2, default=str,
        )
        summary_messages = [
            {
                "role": "system",
                "content": (
                    _SEMANTIKA_SYSTEM_PROMPT
                    + "\n\n"
                    "The user's question was answered by executing a command "
                    "on their behalf. Summarize the result in a friendly, "
                    "natural way. Use markdown formatting for readability.\n\n"
                    "Command executed: !" + " ".join(tokens) + "\n"
                    "Raw result:\n" + result_summary
                ),
            },
            {"role": "user", "content": user_message},
        ]
        return await _safe_chat(summary_messages)

    # ── Phase 1: Try structured command generation ───────────────────────
    defs = get_command_definitions(get_command_tree())
    cmd = None
    try:
        cmd = await provider.generate_command(req.message, defs)
    except Exception:
        cmd = None

    executed_cmd = None  # (tokens, flags, result)

    # Phase 1b: If generate_command returned nothing, try a softer approach
    # — ask the LLM directly what command to run.
    if not cmd or not cmd.get("tokens"):
        probe_msgs = [
            {
                "role": "system",
                "content": (
                    "You MUST translate the user's request into a valid "
                    "command from the list below. This is a question about "
                    "graph data, so there IS a matching command. "
                    "Respond with ONLY a JSON object, no extra text:\n"
                    '{"tokens": ["exact", "path"], "flags": {}}\n\n'
                    + json.dumps(defs, indent=2)
                ),
            },
            {"role": "user", "content": req.message},
        ]
        probe_raw = await _safe_chat(probe_msgs)
        if probe_raw:
            from lightercore.llm.utils import parse_command_result
            probe_cmd = parse_command_result(probe_raw.strip())
            if probe_cmd and probe_cmd.get("tokens"):
                cmd = probe_cmd

    if cmd and cmd.get("tokens"):
        tokens = cmd["tokens"]
        flags = cmd.get("flags", {})

        # Phase 2a: Permission check — gate destructive AND write commands
        cmd_path = ".".join(tokens)
        level = get_command_level(cmd_path)
        is_destructive = level >= PermissionLevel.DESTRUCTIVE
        is_write = _is_write_command(tokens) and not is_destructive
        if is_destructive or is_write:
            meta = get_handler_metadata(cmd_path)
            desc = meta.get("description", "") if meta else ""
            if is_destructive:
                tag = "destructive"
                advice = (
                    "If you do not want this, tell the LLM what to do "
                    "instead (e.g. \"list first\" or \"try a different approach\")."
                )
            else:
                tag = "write"
                advice = (
                    "This command will modify your data. If you prefer a "
                    "different action, tell the LLM (e.g. \"search first\" "
                    "or \"show me what exists\")."
                )
            return {
                "type": "confirm",
                "tokens": tokens,
                "flags": flags,
                "message": (
                    f"The LLM wants to run a **{tag}** command "
                    f"(`!{' '.join(tokens)}`).\n\n"
                    f"{desc}\n\n"
                    f"{advice}"
                ),
            }

        # Phase 2b: Execute and summarise
        result = await _try_execute(tokens, flags)
        if result is not None:
            executed_cmd = (tokens, flags, result)
        else:
            # Command path was invalid — give the LLM another chance with
            # an error hint so it can correct itself.
            correction_prompt = (
                "I tried to run the command `!" + " ".join(tokens)
                + "` but that exact path does not exist. "
                "Here are the available commands. "
                "Please translate the user's request into a correct command "
                "from this list. Use ONLY exact paths from the list.\n\n"
                + json.dumps(defs, indent=2)
            )
            retry_msgs = [
                {"role": "system", "content": correction_prompt},
                {"role": "user", "content": req.message},
            ]
            retry_raw = await _safe_chat(retry_msgs)
            if retry_raw:
                from lightercore.llm.utils import parse_command_result
                retry_cmd = parse_command_result(retry_raw.strip())
                if retry_cmd and retry_cmd.get("tokens"):
                    retry_result = await _try_execute(
                        retry_cmd["tokens"], retry_cmd.get("flags", {}),
                    )
                    if retry_result is not None:
                        executed_cmd = (
                            retry_cmd["tokens"],
                            retry_cmd.get("flags", {}),
                            retry_result,
                        )

    # ── Phase 3: Summarise if we have a successful execution ─────────────
    if executed_cmd is not None:
        tokens, flags, result = executed_cmd
        reply = await _summarise(tokens, result, req.message)
        if reply:
            return {"reply": reply}

    # ── Phase 4: Plain chat with system context ──────────────────────────
    plain = await _safe_chat(_build_chat_messages(messages, req.message))
    if plain:
        return {"reply": plain}

    return {"reply": _stub_response(req.message)["reply"]}


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


# ── Semantika system prompt ──────────────────────────────────────────────


_SEMANTIKA_SYSTEM_PROMPT = (
    "You are Semantika AI, the built-in assistant of the **Semantika "
    "knowledge graph** application. You run INSIDE the app and can "
    "execute commands to look up data the user asks about.\n\n"
    "## What Semantika Is\n"
    "Semantika stores structured knowledge as:\n"
    "- **Nodes** — entities or concepts\n"
    "- **Predicates** — relationship types between nodes\n"
    "- **Triples** — subject-predicate-object statements\n\n"
    "## Available Commands\n"
    "- `!node` — list, add, search, show, edit, delete, merge nodes\n"
    "- `!predicate` — list, add, search, show, edit, delete predicates\n"
    "- `!triple` — list, add, search, show, edit, delete triples\n"
    "- `!search` — full-text search\n"
    "- `!stats` — show graph statistics\n"
    "- `!export` — export as Turtle (.ttl)\n"
    "- `!unit` — manage units/ontology\n"
    "- `!backup` — backup management\n\n"
    "## How to Respond\n"
    "- When the user asks about their graph data (domains, content, "
    "what exists, what kind of X), the system will try to execute a "
    "command on your behalf. If that happened, you will see the "
    "command and its raw result in your system message. Use that data "
    "to answer — do NOT tell the user to run commands themselves.\n"
    "- If you see raw data in the system message, ANALYZE it and "
    "present the answer directly. For example, if you see a list of "
    "nodes, categorize them by domain and explain what you found.\n"
    "- NEVER just tell the user to run a command like \"try !node "
    "list\". If the data was fetched, you already have it — use it.\n"
    "- Keep responses concise and helpful. Use Markdown formatting.\n"
    "- Never invent data. If you truly have no data, say so clearly."
)


def _build_chat_messages(
    messages: list[dict],
    user_message: str,
) -> list[dict]:
    """Build message list with Semantika system context prepended."""
    return [
        {"role": "system", "content": _SEMANTIKA_SYSTEM_PROMPT},
        *messages,
        {"role": "user", "content": user_message},
    ]


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
