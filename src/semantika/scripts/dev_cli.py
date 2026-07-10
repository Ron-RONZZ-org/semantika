"""Development CLI — starts an isolated server with optional seed data.

Uses ``lightercore.dev_helpers`` for shared dev-server infrastructure
(``--data-dir``, ``--seed``, ``--prod``, temp dir management, cleanup).

Usage::

    # Start with seed data from .dev (prompt commands + LLM config)
    uv run semantika-dev --seed

    # Start with seed data from .prod (your real LLM key)
    uv run semantika-dev --prod

    # Start with persistent data directory
    uv run semantika-dev --data-dir ~/semantika-data --seed

    # Start without seed data, skip user hooks
    uv run semantika-dev --no-hooks
"""

from __future__ import annotations

import os
from pathlib import Path

from lightercore.dev_helpers import (
    cleanup_data_dir,
    find_dot_dev,
    find_dot_prod,
    is_seeded,
    setup_data_dir,
    standard_dev_parser,
    validate_seed_sources,
)


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

    # Seed the two-turn prompt files for /template
    # Always overwrite — these are app-internal prompts, not user config.
    template_turns_dir = commands_dir / "_template_turns"
    template_turns_dir.mkdir(parents=True, exist_ok=True)
    turn1_file = template_turns_dir / "turn1.md"
    turn1_file.write_text(
        "# turn1 — predicate discovery\n"
        "Your task is to find existing predicates in the Semantika "
        "knowledge graph that are relevant to the user's template "
        "description.\n\n"
        "User description:\n"
        "$ARGUMENTS\n\n"
        "Use the **predicate.search** tool to find relevant predicates. "
        "Try different keyword variations to get broad coverage. "
        "Once you have a good set, list the predicate IDs you found.\n",
        encoding="utf-8",
    )
    turn2_file = template_turns_dir / "turn2.md"
    turn2_file.write_text(
        "# turn2 — YAML template generation\n"
        "Generate a YAML template definition matching the user's description "
        "using the predicates found, then save it with ``template.save``.\n\n"
        "## Template Schema\n"
        "```yaml\n"
        "name: <short-name>\n"
        "description: <short-description>\n"
        "params:\n"
        "  - name: <variable-name>\n"
        "    label: <human-label>\n"
        "    type: node | string | number\n"
        "    required: true\n"
        "triples:\n"
        '  - "{var1} {predicate1} {var2}"           # URI (node ref)\n'
        '  - "{var1} {predicate2} {var3} --str"     # string literal\n'
        '  - "{var1} {predicate3} {var4} --int"     # number literal\n'
        "```\n\n"
        "## Rules\n"
        "- No flag = URI reference (object is another node)\n"
        "- `--str` = string literal, `--int` = number literal\n"
        "- Optional params: if not filled, the triple is auto-skipped\n"
        "- Use PREDICATE IDs that already exist in your graph\n\n"
        "## Predicates found\n"
        "$1\n\n"
        "## User description\n"
        "$2\n\n"
        "## Instructions\n"
        "1. Generate the YAML template content.\n"
        "2. Call **template.save** with ``--yaml`` set to the full YAML "
        "content to persist it to disk.\n"
        "3. The user will be asked to confirm — explain what the template "
        "contains so they can make an informed decision.\n"
        "4. After the tool completes, summarise what was created.\n\n"
        "You may also call **template.list** to check existing templates "
        "or **predicate.search** to verify predicate IDs.\n",
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


def _auto_configure_llm(creds: dict[str, str]) -> None:
    """Configure the LLM provider from credentials on fresh seed.

    Always overwrites any existing keyring config because this function
    is only called during ``--seed`` / ``--prod`` with a fresh (empty)
    data directory — stale configs from previous test runs or broken
    seeds must not block the live key.
    """
    api_key = creds.get("DEEPSEEK_API_KEY", "") or creds.get("TEST_DEEPSEEK_APIKEY", "")
    if not api_key:
        return

    from lightercore.llm.config import save_active_config as _save
    from lightercore.llm.config import ProviderConfig

    SERVICE = "semantika-llm"

    config = ProviderConfig(
        provider_type="deepseek",
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        temperature=0.7,
        max_tokens=4096,
    )
    _save(SERVICE, config)


def dev_main() -> None:
    """Run an isolated Semantika dev server.

    By default creates a temporary data directory (``/tmp/semantika-dev-*``)
    and optionally seeds it with test data before starting the server.

    Flags:
    - ``--data-dir PATH`` — keep data persistent across restarts.
    - ``--local-config PATH`` — use a custom config directory for testing
      prompt command / AGENTS.md / hooks changes.  Overrides any config
      dir set by ``--data-dir``.  Useful for iterating on config files
      stored in a git checkout.
    - ``--no-hooks`` — skip loading user hooks.
    """
    parser = standard_dev_parser(
        "Run an isolated Semantika development server.",
        default_port=6015,
    )
    parser.add_argument("--no-hooks", action="store_true",
                        help="Skip loading user-defined hooks from ~/.config/semantika/hooks.py")
    parser.add_argument("--local-config", type=str, default=None,
                        help="Use a local config directory (e.g. a git checkout) "
                             "for prompt commands, AGENTS.md, user hooks, and "
                             "template turn prompts. Overrides the config dir "
                             "from --data-dir if both are given.")
    args = parser.parse_args()

    validate_seed_sources(args)

    LOG_PREFIX = "[semantika-dev]"

    def _log(msg: str) -> None:
        if not args.quiet:
            print(f"{LOG_PREFIX} {msg}")

    # Resolve port: CLI arg > SEMANTIKA_PORT env var > 6015
    port = args.port or int(os.environ.get("SEMANTIKA_PORT", 6015))

    # ── Setup data directory ──────────────────────────────────────────────
    root_dir, data_dir, config_dir, is_temp = setup_data_dir(
        args.data_dir, app_name="semantika",
    )

    # --local-config overrides the config dir set by --data-dir or the
    # default temp dir.  This lets you test config changes (prompt commands,
    # AGENTS.md, hooks, template turn prompts) from a working directory
    # without touching your real ~/.config/semantika/.
    if args.local_config:
        local_config = Path(args.local_config).expanduser().resolve()
        local_config.mkdir(parents=True, exist_ok=True)
        os.environ["SEMANTIKA_CONFIG_DIR"] = str(local_config)
        config_dir = local_config
        _log(f"Local config dir: {config_dir} (overrides configured config dir)")
    else:
        _log(f"Config dir: {config_dir}")

    _log(f"Data dir: {data_dir}")

    already_seeded = is_seeded(data_dir)

    # ── Seed from .dev ───────────────────────────────────────────────────
    if args.seed is not None:
        if already_seeded:
            _log("Data dir already has content — skipping seed.")
        else:
            if args.seed == "auto":
                dot_dev = find_dot_dev(__file__)
                if dot_dev is None:
                    print(f"{LOG_PREFIX} WARNING: No .dev file found. Seeding skipped.")
                    dot_dev = None
                else:
                    _log(f"Using .dev file: {dot_dev}")
            else:
                dot_dev = Path(args.seed)
                if not dot_dev.exists():
                    print(f"{LOG_PREFIX} ERROR: .dev file not found: {dot_dev}")
                    raise SystemExit(1)
                _log(f"Using .dev file: {dot_dev}")

            if dot_dev:
                creds = _parse_dot_dev(dot_dev)
                _seed_prompt_commands()
                _auto_configure_llm(creds)
                _log("Seeded prompt commands, templates, and LLM config.")

    # ── Seed from .prod ──────────────────────────────────────────────────
    elif args.prod is not None:
        if already_seeded:
            _log("Data dir already has content — skipping prod-seed.")
        else:
            if args.prod == "auto":
                dot_prod = find_dot_prod(__file__)
                if dot_prod is None:
                    print(f"{LOG_PREFIX} WARNING: No .prod file found. Seeding skipped.")
                    dot_prod = None
                else:
                    _log(f"Using .prod file: {dot_prod}")
            else:
                dot_prod = Path(args.prod)
                if not dot_prod.exists():
                    print(f"{LOG_PREFIX} ERROR: .prod file not found: {dot_prod}")
                    raise SystemExit(1)
                _log(f"Using .prod file: {dot_prod}")

            if dot_prod:
                creds = _parse_dot_dev(dot_prod)
                _seed_prompt_commands()
                _auto_configure_llm(creds)
                _log("Seeded prompt commands, templates, and LLM config from .prod.")

    # ── Start server ─────────────────────────────────────────────────────
    _log(f"Starting server on http://127.0.0.1:{port}")
    _log("Press Ctrl+C to stop.")

    import uvicorn

    # Pass no_hooks via env var (needed because uvicorn >= 0.30 requires an
    # import string, not an app instance, when reload=True).
    if args.no_hooks:
        os.environ["SEMANTIKA_NO_HOOKS"] = "1"

    try:
        uvicorn.run(
            "semantika.server.app:create_app",
            host="127.0.0.1",
            port=port,
            reload=False,
            factory=True,
        )
    finally:
        cleanup_data_dir(
            root_dir, is_temp, args.keep_data,
            quiet=args.quiet, log_prefix=LOG_PREFIX,
        )


def _parse_dot_dev(dot_dev_path: str | Path | None) -> dict[str, str]:
    """Parse a ``.dev`` or ``.prod`` file into a dict of key→value."""
    result: dict[str, str] = {}
    if dot_dev_path is None:
        return result
    path = Path(dot_dev_path)
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result


if __name__ == "__main__":
    dev_main()
