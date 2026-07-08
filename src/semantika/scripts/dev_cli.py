"""Development CLI — starts an isolated server with optional seed data."""

from __future__ import annotations

import argparse

import uvicorn


def _seed_prompt_commands() -> None:
    """Create demo prompt command files and a sample triple template."""
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

    # Seed the /template prompt command (description shown in autocomplete;
    # actual execution is handled by the backend's two-turn flow).
    template_file = commands_dir / "template.md"
    if not template_file.exists():
        template_file.write_text(
            "# Generate a reusable triple template\n"
            "Creates a YAML template for adding multiple triples at once. "
            "Describe the data structure (e.g. \"books with author, ISBN, title\").\n",
            encoding="utf-8",
        )

    # Seed a sample YAML triple template for testing
    templates_dir = config_dir() / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)
    book_template = templates_dir / "book.yaml"
    if not book_template.exists():
        book_template.write_text(
            "name: book\n"
            "description: Add a book with author, ISBN, and title\n"
            "params:\n"
            "  - name: subject\n"
            "    label: Book node\n"
            "    type: node\n"
            "    required: true\n"
            "  - name: author\n"
            "    label: Author\n"
            "    type: node\n"
            "    required: true\n"
            "  - name: isbn\n"
            "    label: ISBN\n"
            "    type: string\n"
            "    required: true\n"
            "  - name: title\n"
            "    label: Title\n"
            "    type: string\n"
            "    required: true\n"
            "triples:\n"
            '  - "{subject} hasAuthor {author}"\n'
            '  - "{subject} hasISBN {isbn} --str"\n'
            '  - "{subject} hasTitle {title} --str"\n',
            encoding="utf-8",
        )


def dev_main() -> None:
    parser = argparse.ArgumentParser(description="Semantika dev server")
    parser.add_argument("--port", type=int, default=6015, help="Port to bind (lighterbird uses 8000)")
    parser.add_argument("--seed", action="store_true", help="Seed a demo prompt command file")
    parser.add_argument("--no-hooks", action="store_true",
                        help="Skip loading user-defined hooks from ~/.config/semantika/hooks.py")
    args = parser.parse_args()

    if args.seed:
        _seed_prompt_commands()
        print("  Seeded demo prompt command, /template command, and sample book template.")

    print(f"Starting Semantika dev server on http://127.0.0.1:{args.port}")
    from semantika.server.app import create_app

    app = create_app(no_hooks=args.no_hooks)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    dev_main()
