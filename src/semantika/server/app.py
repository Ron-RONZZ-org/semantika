"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def create_app() -> FastAPI:
    app = FastAPI(title="Semantika", version="0.1.0")

    # API routes
    from semantika.server.routes import command, graph, llm, query

    app.include_router(graph.router, prefix="/api/v1/graph")
    app.include_router(query.router, prefix="/api/v1/query")
    app.include_router(command.router, prefix="/api/v1/command")
    app.include_router(llm.router, prefix="/api/v1/llm")

    # Static files (Svelte SPA)
    import os
    from pathlib import Path

    dist = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app
