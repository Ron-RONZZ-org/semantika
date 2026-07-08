"""FastAPI application factory."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from semantika.graph.db import init_db

logger = logging.getLogger(__name__)


def _cors_config() -> tuple[list[str], bool]:
    """Return (origins, allow_credentials) from env var or dev defaults.

    Set ``SEMANTIKA_CORS_ORIGINS`` to a comma-separated list of origins,
    e.g. ``https://app.semantika.local,http://localhost:6016``.
    Defaults to localhost dev ports for safe development.
    """
    raw = os.environ.get("SEMANTIKA_CORS_ORIGINS", "").strip()
    if not raw:
        logger.info(
            "SEMANTIKA_CORS_ORIGINS not set — defaulting to localhost dev ports. "
            "Set this env var to your frontend origin(s) in production."
        )
        return ["http://localhost:6016", "http://127.0.0.1:6016"], True
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if origins == ["*"]:
        return ["*"], False
    return origins, True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: init DB, backup scheduler, ensure template dir."""
    init_db()
    try:
        from semantika.server.tasks import init_backup_scheduler
        init_backup_scheduler()
    except Exception:
        logger.warning("Backup scheduler init failed (non-fatal)")
    # Ensure templates directory exists
    try:
        from lightercore.paths import config_dir
        (config_dir() / "templates").mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.warning("Could not create templates dir (non-fatal)")
    yield
    try:
        from semantika.server.tasks import shutdown_backup_scheduler
        shutdown_backup_scheduler(timeout=3.0)
    except Exception:
        logger.warning("Backup scheduler shutdown failed (non-fatal)")


def create_app() -> FastAPI:
    app = FastAPI(title="Semantika", version="0.1.0", lifespan=lifespan)

    # CORS — restrict via SEMANTIKA_CORS_ORIGINS env var in production
    origins, allow_creds = _cors_config()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_creds,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes — import triggers @command decorators (system handlers register)
    from semantika.server.routes import command as cmd
    from semantika.server.routes import files, graph, llm, prompt_commands, proof, query, review, unit
    from semantika.server.routes import user_config as ucfg
    from semantika.server.routes import triple_templates as tpl

    app.include_router(graph.router, prefix="/api/v1/graph")
    app.include_router(query.router, prefix="/api/v1/query")
    app.include_router(cmd.router, prefix="/api/v1/command")
    app.include_router(review.router, prefix="/api/v1/review")
    app.include_router(proof.router, prefix="/api/v1/proof")
    app.include_router(llm.router, prefix="/api/v1/llm")
    app.include_router(unit.router, prefix="/api/v1")
    app.include_router(files.router, prefix="/api/v1/files")
    app.include_router(prompt_commands.router)
    app.include_router(ucfg.router)
    app.include_router(tpl.router)

    # Freeze system handlers, then load user hooks
    from semantika.server.command.registry import freeze_system_commands, load_user_hooks
    freeze_system_commands()
    load_user_hooks()

    # Static files (Svelte SPA) — overridable via SEMANTIKA_STATIC_DIR
    static_dir = os.environ.get("SEMANTIKA_STATIC_DIR") or (
        Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"
    )
    static_path = Path(static_dir)
    if static_path.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(static_path), html=True),
            name="static",
        )

    return app
