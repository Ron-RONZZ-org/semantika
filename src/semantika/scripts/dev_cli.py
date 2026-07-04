"""Development CLI — starts an isolated server with optional seed data."""

from __future__ import annotations

import argparse
import sys
import tempfile

import uvicorn


def dev_main() -> None:
    parser = argparse.ArgumentParser(description="Semantika dev server")
    parser.add_argument("--seed", action="store_true", help="Seed with test data")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    args = parser.parse_args()

    # TODO: seed data logic
    if args.seed:
        print("Seeding test data... (not yet implemented)")

    print(f"Starting Semantika dev server on http://127.0.0.1:{args.port}")
    from semantika.server.app import create_app

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    dev_main()
