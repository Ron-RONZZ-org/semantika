"""LLM integration routes — chat, natural-language query."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = ""
    history: list[dict] = []


@router.post("/chat")
async def chat(req: ChatRequest):
    """Free-form conversation with the LLM, which may query the graph.

    For now, this is a stub that responds with graph data.
    LLM provider integration (OpenAI/Ollama) will be added in a follow-up.
    """
    message = req.message.strip().lower()

    # Simple keyword-based responses (LLM native integration TBD)
    from semantika.graph.db import get_services

    if "stats" in message or "count" in message or "how many" in message:
        stats = get_services()["triple"].get_stats()
        return {
            "reply": (
                f"Your knowledge graph has **{stats['nodes']}** nodes, "
                f"**{stats['predicates']}** predicates, and "
                f"**{stats['triples']}** triples."
            )
        }

    if "search" in message or "find" in message or "look for" in message:
        # Extract the query — everything after the verb
        for prefix in ["search for ", "search ", "find ", "look for "]:
            if prefix in message:
                q = message.split(prefix, 1)[1].strip()
                break
        else:
            q = req.message.strip()
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

    if "help" in message or "what can you" in message:
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
            "I'm a stub LLM integration. In production, I'd connect to an "
            "OpenAI-compatible API or Ollama. For now, try keywords like "
            "\"stats\", \"search\", or \"help\"."
        )
    }
