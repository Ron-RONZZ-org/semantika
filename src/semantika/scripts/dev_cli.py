"""Development CLI — starts an isolated server with optional seed data."""

from __future__ import annotations

import argparse

import uvicorn


def _seed_prompt_commands() -> None:
    """Create a demo prompt command file for development/testing."""
    from lightercore.paths import config_dir

    commands_dir = config_dir() / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    demo_file = commands_dir / "demo.md"
    if not demo_file.exists():
        demo_file.write_text(
            "# Demo prompt command for testing\n"
            "This is a sample prompt command for testing purposes.\n"
            "The argument passed was: $1\n",
            encoding="utf-8",
        )


def dev_main() -> None:
    parser = argparse.ArgumentParser(description="Semantika dev server")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind (lighterbird uses 8000)")
    parser.add_argument("--seed", action="store_true", help="Seed a demo prompt command file")
    args = parser.parse_args()

    if args.seed:
        _seed_prompt_commands()
        print("  Seeded demo prompt command.")

    print(f"Starting Semantika dev server on http://127.0.0.1:{args.port}")
    from semantika.server.app import create_app

    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    dev_main()
