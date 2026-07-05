"""FastAPI application factory."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from semantika.graph.db import init_db


def _resolve_cors_origins() -> list[str]:
    """Return CORS origins from env var, or ``["*"]`` as fallback.

    Set ``SEMANTIKA_CORS_ORIGINS`` to a comma-separated list of origins,
    e.g. ``https://app.semantika.local,http://localhost:5173``.
    In production, restrict this to your actual frontend domain(s).
    """
    raw = os.environ.get("SEMANTIKA_CORS_ORIGINS", "").strip()
    if not raw:
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="Semantika", version="0.1.0")

    # CORS — restrict via SEMANTIKA_CORS_ORIGINS env var in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize DB on startup
    @app.on_event("startup")
    async def startup() -> None:
        init_db()
        try:
            from semantika.server.tasks import init_backup_scheduler
            init_backup_scheduler()
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Backup scheduler init failed (non-fatal)"
            )

    @app.on_event("shutdown")
    async def shutdown() -> None:
        try:
            from semantika.server.tasks import shutdown_backup_scheduler
            shutdown_backup_scheduler(timeout=3.0)
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Backup scheduler shutdown failed (non-fatal)"
            )

    # API routes
    from semantika.server.routes import graph, query, command as cmd, review, proof, llm, unit, files

    app.include_router(graph.router, prefix="/api/v1/graph")
    app.include_router(query.router, prefix="/api/v1/query")
    app.include_router(cmd.router, prefix="/api/v1/command")
    app.include_router(review.router, prefix="/api/v1/review")
    app.include_router(proof.router, prefix="/api/v1/proof")
    app.include_router(llm.router, prefix="/api/v1/llm")
    app.include_router(unit.router, prefix="/api/v1")
    app.include_router(files.router, prefix="/api/v1/files")

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
