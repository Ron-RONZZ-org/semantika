"""Command handlers for LLM configuration commands."""

from __future__ import annotations
from lightercore.permissions import PermissionLevel

from typing import Any

from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command, group_command
from semantika.server.llm.provider import get_provider


@group_command("llm", description="Manage LLM provider configuration")
def cmd_llm_root(remaining: list[str], flags: dict[str, str]) -> dict:
    return {"type": "status", "title": "LLM Commands", "data": {
        "_summary": "Available !llm commands:\n  !llm show — Show current config\n  !llm new <protocol> — Create config\n  !llm set [flags] — Modify settings\n  !llm clear — Clear config\n  !llm profiles — List profiles\n  !llm profile list — List profiles\n  !llm profile show — Show active profile\n  !llm profile load <name> — Load profile\n  !llm profile delete <name> — Delete profile"}}


@command("llm.show", description="Show current LLM configuration",
         permission_level=PermissionLevel.READ)
def cmd_llm_show(remaining: list[str], flags: dict[str, str]) -> dict:
    p = get_provider()
    cfg = p.config
    return {"type": "status", "title": "LLM Configuration", "data": {
        "provider_type": cfg.provider_type, "has_api_key": bool(cfg.api_key),
        "base_url": cfg.base_url, "model": cfg.model, "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens, "available": p.available}}


@command("llm.new", description="Create new LLM configuration",
         params=[{"name": "provider_type", "type": "string", "required": True}],
         flags=[{"name": "api_key", "type": "string"}, {"name": "base_url", "type": "string"},
                {"name": "model", "type": "string"}, {"name": "alias", "type": "string"}])
def cmd_llm_new(remaining: list[str], flags: dict[str, str]) -> dict:
    p = get_provider()
    protocol = flags.get("provider_type") or (remaining[0] if remaining else "") or ""
    if not protocol:
        raise CommandValidationError("Missing protocol.", "Usage: !llm new openai|deepseek|ollama|custom [--api-key KEY]")
    p.configure(provider_type=protocol, api_key=flags.get("api_key", ""), base_url=flags.get("base_url", ""),
                model=flags.get("model", ""), temperature=float(flags.get("temperature", 0.7)),
                max_tokens=int(flags.get("max_tokens", 2048)))
    result: dict[str, Any] = {"protocol": protocol, "available": p.available}
    if "alias" in flags:
        name = flags["alias"]
        cfg = p.config
        p.save_profile(name=name, provider_type=cfg.provider_type, api_key=cfg.api_key or "",
                       base_url=cfg.base_url or "", model=cfg.model or "",
                       temperature=cfg.temperature, max_tokens=cfg.max_tokens)
        result["saved_as"] = name
    return {"type": "status", "title": "LLM Configured", "data": result}


@command("llm.set", description="Modify current LLM settings",
         flags=[{"name": "api_key", "type": "string"}, {"name": "base_url", "type": "string"},
                {"name": "model", "type": "string"}, {"name": "alias", "type": "string"}])
def cmd_llm_set(remaining: list[str], flags: dict[str, str]) -> dict:
    p = get_provider()
    if not flags:
        raise CommandValidationError("No settings provided.", "Usage: !llm set --model gpt-4 --api-key sk-...")
    cfg = p.config
    p.configure(provider_type=flags.get("provider_type", cfg.provider_type or "deepseek"),
                api_key=flags.get("api_key", cfg.api_key or ""), base_url=flags.get("base_url", cfg.base_url or ""),
                model=flags.get("model", cfg.model or ""),
                temperature=float(flags.get("temperature", cfg.temperature or 0.7)),
                max_tokens=int(flags.get("max_tokens", cfg.max_tokens or 2048)))
    result: dict[str, Any] = {"_summary": "done"}
    if "alias" in flags:
        name = flags["alias"]
        c = p.config
        p.save_profile(name=name, provider_type=c.provider_type, api_key=c.api_key or "",
                       base_url=c.base_url or "", model=c.model or "",
                       temperature=c.temperature, max_tokens=c.max_tokens)
        result["saved_as"] = name
    return {"type": "status", "title": "Profile Updated", "data": result}


@command("llm.clear", description="Clear LLM configuration")
def cmd_llm_clear(remaining: list[str], flags: dict[str, str]) -> dict:
    p = get_provider()
    p.clear_config()
    return {"type": "status", "title": "LLM Cleared", "data": {"_summary": "done"}}


@command("llm.profiles", description="List saved LLM profiles",
         permission_level=PermissionLevel.READ)
def cmd_llm_profiles(remaining: list[str], flags: dict[str, str]) -> dict:
    p = get_provider()
    profiles = p.list_profiles()
    return {"type": "status", "title": "LLM Profiles", "data": {"profiles": profiles, "active_profile": p.active_profile_name}}


@command("llm.profile.list", description="List saved LLM profiles",
         permission_level=PermissionLevel.READ)
def cmd_llm_profile_list(remaining: list[str], flags: dict[str, str]) -> dict:
    p = get_provider()
    profiles = p.list_profiles()
    return {"type": "status", "title": "LLM Profiles", "data": {"profiles": profiles, "active_profile": p.active_profile_name}}


@command("llm.profile.show", description="Show active LLM profile",
         permission_level=PermissionLevel.READ)
def cmd_llm_profile_show(remaining: list[str], flags: dict[str, str]) -> dict:
    p = get_provider()
    cfg = p.config
    return {"type": "status", "title": "Active Profile", "data": {
        "provider_type": cfg.provider_type, "has_api_key": bool(cfg.api_key), "base_url": cfg.base_url,
        "model": cfg.model, "temperature": cfg.temperature, "max_tokens": cfg.max_tokens,
        "available": p.available, "active_profile_name": p.active_profile_name}}


@command("llm.profile.load", description="Load a saved LLM profile",
         params=[{"name": "name", "type": "string", "required": True}])
def cmd_llm_profile_load(remaining: list[str], flags: dict[str, str]) -> dict:
    name = flags.get("name") or (remaining[0] if remaining else "") or ""
    if not name:
        raise CommandValidationError("Missing profile name.", "Usage: !llm profile load <name>")
    p = get_provider()
    config = p.switch_to_profile(name)
    if config is None:
        raise CommandValidationError(f"Profile not found: {name}")
    return {"type": "status", "title": "Profile Loaded",
            "data": {"name": name, "protocol": config.provider_type, "model": config.model, "available": p.available}}


@command("llm.profile.delete", description="Delete a saved LLM profile",
         params=[{"name": "name", "type": "string", "required": True}])
def cmd_llm_profile_delete(remaining: list[str], flags: dict[str, str]) -> dict:
    name = flags.get("name") or (remaining[0] if remaining else "") or ""
    if not name:
        raise CommandValidationError("Missing profile name.", "Usage: !llm profile delete <name>")
    p = get_provider()
    if p.delete_profile(name):
        return {"type": "status", "title": "Profile Deleted", "data": {"removed": [name]}}
    raise CommandValidationError(f"Profile not found: {name}")
