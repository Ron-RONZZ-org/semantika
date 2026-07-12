"""API routes for user configuration — GET/PATCH /api/v1/user/config."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from semantika.server.user_config import (
    get_bool,
    get_locale,
    load_config,
    set_bool,
    set_locale,
)

router = APIRouter(prefix="/api/v1/user")


class ConfigUpdate(BaseModel):
    locale: str | None = None
    normalise_node_ids: bool | None = None
    strip_diacritics_from_predicate_ids: bool | None = None


@router.get("/config")
def get_user_config():
    """Return current user configuration."""
    cfg = load_config()
    return {
        "locale": cfg.get("locale", "en"),
        "normalise_node_ids": get_bool("normalise_node_ids", False),
        "strip_diacritics_from_predicate_ids": get_bool("strip_diacritics_from_predicate_ids", False),
    }


@router.patch("/config")
def update_user_config(data: ConfigUpdate):
    """Update user configuration."""
    if data.locale is not None:
        if len(data.locale) < 2 or len(data.locale) > 5:
            raise HTTPException(
                status_code=400,
                detail="Locale should be 2-5 characters (e.g. 'en', 'fr', 'en-US')",
            )
        set_locale(data.locale)
    if data.normalise_node_ids is not None:
        set_bool("normalise_node_ids", data.normalise_node_ids)
    if data.strip_diacritics_from_predicate_ids is not None:
        set_bool("strip_diacritics_from_predicate_ids", data.strip_diacritics_from_predicate_ids)
    return {
        "locale": get_locale(),
        "normalise_node_ids": get_bool("normalise_node_ids", False),
        "strip_diacritics_from_predicate_ids": get_bool("strip_diacritics_from_predicate_ids", False),
    }
