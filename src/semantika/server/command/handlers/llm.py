"""Command handlers for LLM configuration commands."""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel

from semantika.server.command.errors import CommandValidationError
from semantika.server.command.registry import command, group_command
from semantika.server.llm.provider import get_provider


@group_command("llm", description="Manage LLM provider configuration")
def cmd_llm_root(remaining: list[str], flags: dict[str, str]) -> dict:
    return {"type": "status", "title": "LLM Commands", "data": {
        "_summary": "Available !llm commands:\n  !llm show — Show current config\n  !llm new <protocol> — Create config\n  !llm set [flags] — Modify settings\n  !llm clear — Clear config\n  !llm profile list — List profiles\n  !llm profile show — Show active profile\n  !llm profile load <name> — Load profile\n  !llm profile delete <name> — Delete profile"}}


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
         flags=[{"name": "api_key", "type": "string", "help": "API key for the provider"}, {"name": "base_url", "type": "string", "help": "Custom API base URL"},
                {"name": "model", "type": "string", "help": "Model name/slug"}, {"name": "alias", "type": "string", "help": "Display alias for this profile"}])
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
         flags=[{"name": "api_key", "type": "string", "help": "API key for the provider"}, {"name": "base_url", "type": "string", "help": "Custom API base URL"},
                {"name": "model", "type": "string", "help": "Model name/slug"}, {"name": "alias", "type": "string", "help": "Display alias for this profile"}])
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


@command("llm.profile.list", description="List saved LLM profiles",
         permission_level=PermissionLevel.READ)
def cmd_llm_profile_list(remaining: list[str], flags: dict[str, str]) -> dict:
    p = get_provider()
    raw_profiles = p.list_profiles()
    active = p.active_profile_name or ""
    return {
        "type": "status",
        "title": "LLM Profiles",
        "data": {
            "profiles": raw_profiles,
            "active_profile": active,
        },
    }


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


# ── !llm prompt commands ──────────────────────────────────────────────────────


@command("llm.prompt.list",
         description="List all customizable prompt files and their modification status",
         permission_level=PermissionLevel.READ)
def cmd_llm_prompt_list(remaining: list[str], flags: dict[str, str]) -> dict:
    """List all prompt files with their current status.

    Returns a ``prompt-list`` type so the frontend opens PromptListTab.
    """
    from semantika.server.llm.prompt_defaults import get_prompt_files_manager
    mgr = get_prompt_files_manager()
    entries = mgr.list_all()
    modified_count = sum(1 for e in entries if e["is_modified"])
    return {
        "type": "prompt-list",
        "title": "Custom Prompt Files",
        "data": {
            "prompts": entries,
            "count": len(entries),
            "modified_count": modified_count,
        },
    }


@command("llm.prompt.view",
         description="View the current content of a prompt file",
         params=[{"name": "name", "type": "string", "required": True, "description": "Prompt file name (e.g. system-prompt, agents, template/turn1)"}],
         permission_level=PermissionLevel.READ)
def cmd_llm_prompt_view(remaining: list[str], flags: dict[str, str]) -> dict:
    """View the full contents of a specific prompt file."""
    name = flags.get("name", "").strip() or (remaining[0] if remaining else "")
    if not name:
        raise CommandValidationError(
            "Missing prompt name.",
            "Usage: !llm prompt view <name>\n"
            "Run !llm prompt list to see available names.",
        )

    from semantika.server.llm.prompt_defaults import get_prompt_files_manager
    mgr = get_prompt_files_manager()

    # Resolve name (accept either the raw name or a display variant)
    default_content = mgr.get_default(name)
    if default_content is None:
        # Try partial match
        all_entries = mgr.list_all()
        known = [e["name"] for e in all_entries]
        raise CommandValidationError(
            f"Unknown prompt '{name}'. Available: {', '.join(known)}"
        )

    content = mgr.get_content(name)
    entry = next((e for e in mgr.list_all() if e["name"] == name), {})
    return {
        "type": "status",
        "title": f"Prompt: {name}",
        "data": {
            "name": name,
            "relative_path": entry.get("relative_path", ""),
            "category": entry.get("category", ""),
            "current": content or "",
            "default": default_content,
            "exists": entry.get("exists", False),
            "is_modified": entry.get("is_modified", False),
        },
    }


@command("llm.prompt.reset",
         description="Reset a prompt file to its shipped default",
         params=[{"name": "name", "type": "string", "required": True, "description": "Prompt file name or --all to reset everything"}],
         flags=[{"name": "all", "type": "flag", "help": "Reset ALL prompt files to defaults"}])
def cmd_llm_prompt_reset(remaining: list[str], flags: dict[str, str]) -> dict:
    """Reset one or all prompt files to their shipped defaults."""
    from semantika.server.llm.prompt_defaults import get_prompt_files_manager
    mgr = get_prompt_files_manager()

    if "all" in flags:
        results = mgr.reset_all()
        success_count = sum(1 for r in results if r["success"])
        return {
            "type": "status",
            "title": "Prompt Reset",
            "data": {
                "message": f"Reset {success_count}/{len(results)} prompt files to defaults",
                "results": results,
            },
        }

    name = flags.get("name", "").strip() or (remaining[0] if remaining else "")
    if not name:
        raise CommandValidationError(
            "Missing prompt name.",
            "Usage: !llm prompt reset <name>  or  !llm prompt reset --all",
        )

    default_content = mgr.get_default(name)
    if default_content is None:
        all_entries = mgr.list_all()
        known = [e["name"] for e in all_entries]
        raise CommandValidationError(
            f"Unknown prompt '{name}'. Available: {', '.join(known)}"
        )

    result = mgr.reset(name)
    if result is None:
        raise CommandValidationError(f"Failed to reset prompt '{name}' — check file permissions.")

    return {
        "type": "status",
        "title": "Prompt Reset",
        "data": {
            "message": f"Prompt '{name}' reset to default",
            "name": name,
        },
    }
