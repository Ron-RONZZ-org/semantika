"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from semantika.graph.db import init_db


def create_app() -> FastAPI:
    app = FastAPI(title="Semantika", version="0.1.0")

    # CORS for dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
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
    from semantika.server.routes import graph, query, command as cmd, review, proof, llm, unit

    app.include_router(graph.router, prefix="/api/v1/graph")
    app.include_router(query.router, prefix="/api/v1/query")
    app.include_router(cmd.router, prefix="/api/v1/command")
    app.include_router(review.router, prefix="/api/v1/review")
    app.include_router(proof.router, prefix="/api/v1/proof")
    app.include_router(llm.router, prefix="/api/v1/llm")
    app.include_router(unit.router, prefix="/api/v1")

    # Static files (Svelte SPA)
    dist = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"
    if dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(dist), html=True),
            name="static",
        )

    return app
