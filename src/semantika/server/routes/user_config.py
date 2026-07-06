"""API routes for user configuration — GET/PATCH /api/v1/user/config."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from semantika.server.user_config import get_locale, load_config, save_config, set_locale

router = APIRouter(prefix="/api/v1/user")


class ConfigUpdate(BaseModel):
    locale: str | None = None


@router.get("/config")
async def get_user_config():
    """Return current user configuration."""
    cfg = load_config()
    return {"locale": cfg.get("locale", "en")}


@router.patch("/config")
async def update_user_config(data: ConfigUpdate):
    """Update user configuration."""
    if data.locale is not None:
        if len(data.locale) < 2 or len(data.locale) > 5:
            raise HTTPException(
                status_code=400,
                detail="Locale should be 2-5 characters (e.g. 'en', 'fr', 'en-US')",
            )
        set_locale(data.locale)
    return {"locale": get_locale()}
